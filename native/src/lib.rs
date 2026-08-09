mod compiler;
mod qir;
mod routing;
mod simulator;
mod types;

use std::fmt::{Display, Formatter};

use serde::Serialize;

pub const ABI_VERSION: &str = "qplanck.native.abi.v1";
pub const CORE_CONTRACT_VERSION: &str = "qplanck.core.contract.v1";
pub const MAX_CONTRACT_REQUEST_BYTES: usize = 32 * 1024 * 1024;

#[derive(Debug)]
pub enum KernelError {
    Invalid(String),
    Resource(String),
    Unsupported(String),
    Internal(String),
}

impl Display for KernelError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Invalid(message)
            | Self::Resource(message)
            | Self::Unsupported(message)
            | Self::Internal(message) => formatter.write_str(message),
        }
    }
}

impl std::error::Error for KernelError {}

impl From<serde_json::Error> for KernelError {
    fn from(error: serde_json::Error) -> Self {
        Self::Invalid(format!("Invalid native kernel request: {error}"))
    }
}

#[derive(Serialize)]
struct ImplementationInfo {
    name: &'static str,
    version: &'static str,
    abi_version: &'static str,
    core_contract_version: &'static str,
    rust_version: &'static str,
    architecture: &'static str,
    operating_system: &'static str,
}

fn implementation_info_value() -> ImplementationInfo {
    ImplementationInfo {
        name: "qplanck-native",
        version: env!("CARGO_PKG_VERSION"),
        abi_version: ABI_VERSION,
        core_contract_version: CORE_CONTRACT_VERSION,
        rust_version: env!("QPLANCK_RUST_VERSION"),
        architecture: std::env::consts::ARCH,
        operating_system: std::env::consts::OS,
    }
}

/// Compile a versioned JSON request without requiring Python.
pub fn compile_contract(request: &[u8]) -> Result<Vec<u8>, KernelError> {
    ensure_request_bound(request)?;
    compiler::compile(request)
}

/// Lower a versioned QIR request without requiring Python.
pub fn lower_qir_contract(request: &[u8]) -> Result<Vec<u8>, KernelError> {
    ensure_request_bound(request)?;
    qir::lower(request)
}

/// Simulate a versioned execution request without requiring Python.
pub fn simulate_contract(request: &[u8]) -> Result<Vec<u8>, KernelError> {
    ensure_request_bound(request)?;
    simulator::simulate(request)
}

fn ensure_request_bound(request: &[u8]) -> Result<(), KernelError> {
    if request.len() > MAX_CONTRACT_REQUEST_BYTES {
        return Err(KernelError::Resource(format!(
            "Native contract request is {} bytes, exceeding the frozen alpha limit of {MAX_CONTRACT_REQUEST_BYTES}.",
            request.len()
        )));
    }
    Ok(())
}

#[cfg(feature = "python")]
mod python {
    use std::panic::{catch_unwind, AssertUnwindSafe};

    use pyo3::exceptions::{PyNotImplementedError, PyOverflowError, PyRuntimeError, PyValueError};
    use pyo3::prelude::*;
    use pyo3::types::{PyBytes, PyModule};

    use super::{
        compile_contract, implementation_info_value, lower_qir_contract, simulate_contract,
        KernelError, ABI_VERSION, CORE_CONTRACT_VERSION,
    };

    fn guarded_bytes<F>(py: Python<'_>, operation: F) -> PyResult<Bound<'_, PyBytes>>
    where
        F: FnOnce() -> Result<Vec<u8>, KernelError>,
    {
        match catch_unwind(AssertUnwindSafe(operation)) {
            Ok(Ok(response)) => Ok(PyBytes::new(py, &response)),
            Ok(Err(KernelError::Invalid(message))) => Err(PyValueError::new_err(message)),
            Ok(Err(KernelError::Resource(message))) => Err(PyOverflowError::new_err(message)),
            Ok(Err(KernelError::Unsupported(message))) => {
                Err(PyNotImplementedError::new_err(message))
            }
            Ok(Err(KernelError::Internal(message))) => Err(PyRuntimeError::new_err(message)),
            Err(_) => Err(PyRuntimeError::new_err(
                "The QCore native kernel panicked; no Python fallback was attempted.",
            )),
        }
    }

    #[pyfunction]
    fn compile_ir<'py>(py: Python<'py>, request: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
        guarded_bytes(py, || compile_contract(request))
    }

    #[pyfunction]
    fn lower_qir<'py>(py: Python<'py>, request: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
        guarded_bytes(py, || lower_qir_contract(request))
    }

    #[pyfunction]
    fn simulate_ir<'py>(py: Python<'py>, request: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
        guarded_bytes(py, || simulate_contract(request))
    }

    #[pyfunction]
    fn implementation_info() -> PyResult<String> {
        serde_json::to_string(&implementation_info_value())
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))
    }

    #[pymodule]
    fn _qplanck_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
        module.add_function(wrap_pyfunction!(compile_ir, module)?)?;
        module.add_function(wrap_pyfunction!(lower_qir, module)?)?;
        module.add_function(wrap_pyfunction!(simulate_ir, module)?)?;
        module.add_function(wrap_pyfunction!(implementation_info, module)?)?;
        module.add("ABI_VERSION", ABI_VERSION)?;
        module.add("CORE_CONTRACT_VERSION", CORE_CONTRACT_VERSION)?;
        Ok(())
    }
}
