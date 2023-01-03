use std::collections::HashMap;

use chrono::{DateTime, Duration, Utc};
use pyo3::{prelude::*, types::PyDict};

use crate::common::pickle_extract;

use super::*;

/// Tumbling windows of fixed duration.
///
/// Args:
///
///   length (datetime.timedelta): Length of window.
///
///   start_at (datetime.datetime): Instant of the first window. You
///       can use this to align all windows to an hour,
///       e.g. Defaults to system time of dataflow start.
///
/// Returns:
///
///   Config object. Pass this as the `window_config` parameter to
///   your windowing operator.
#[pyclass(module="bytewax.window", extends=WindowConfig)]
#[derive(Clone)]
pub(crate) struct TumblingWindowConfig {
    #[pyo3(get)]
    pub(crate) length: chrono::Duration,
    #[pyo3(get)]
    pub(crate) start_at: Option<DateTime<Utc>>,
}

impl WindowBuilder for TumblingWindowConfig {
    fn build(&self, _py: Python) -> StringResult<Builder> {
        Ok(Box::new(TumblingWindower::builder(
            self.length,
            self.start_at.unwrap_or_else(Utc::now),
        )))
    }
}

#[pymethods]
impl TumblingWindowConfig {
    #[new]
    #[args(length, start_at = "None")]
    pub(crate) fn new(
        length: chrono::Duration,
        start_at: Option<DateTime<Utc>>,
    ) -> (Self, WindowConfig) {
        (Self { length, start_at }, WindowConfig {})
    }

    /// Return a representation of this class as a PyDict.
    fn __getstate__(&self) -> HashMap<&str, Py<PyAny>> {
        Python::with_gil(|py| {
            HashMap::from([
                ("type", "TumblingWindowConfig".into_py(py)),
                ("length", self.length.into_py(py)),
                ("start_at", self.start_at.into_py(py)),
            ])
        })
    }

    /// Egregious hack see [`SqliteRecoveryConfig::__getnewargs__`].
    fn __getnewargs__(&self) -> (chrono::Duration, Option<DateTime<Utc>>) {
        (chrono::Duration::zero(), None)
    }

    /// Unpickle from a PyDict
    fn __setstate__(&mut self, state: &PyAny) -> PyResult<()> {
        let dict: &PyDict = state.downcast()?;
        self.length = pickle_extract(dict, "length")?;
        self.start_at = pickle_extract(dict, "start_at")?;
        Ok(())
    }
}

/// Use fixed-length tumbling windows aligned to a start time.
pub(crate) struct TumblingWindower {
    length: Duration,
    start_at: DateTime<Utc>,
    close_times: HashMap<WindowKey, DateTime<Utc>>,
}

impl TumblingWindower {
    pub(crate) fn builder(
        length: Duration,
        start_at: DateTime<Utc>,
    ) -> impl Fn(Option<StateBytes>) -> Box<dyn Windower> {
        move |resume_snapshot| {
            let close_times = resume_snapshot
                .map(StateBytes::de::<HashMap<WindowKey, DateTime<Utc>>>)
                .unwrap_or_default();

            Box::new(Self {
                length,
                start_at,
                close_times,
            })
        }
    }
}

impl Windower for TumblingWindower {
    fn insert(
        &mut self,
        watermark: &DateTime<Utc>,
        item_time: &DateTime<Utc>,
    ) -> Vec<Result<WindowKey, InsertError>> {
        let since_start_at = *item_time - self.start_at;
        let window_count = since_start_at.num_milliseconds() / self.length.num_milliseconds();

        let key = WindowKey(window_count);
        let close_at = self
            .start_at
            .checked_add_signed(self.length * (window_count as i32 + 1))
            .unwrap_or(DateTime::<Utc>::MAX_UTC);

        if &close_at < watermark {
            vec![Err(InsertError::Late(key))]
        } else {
            self.close_times
                .entry(key)
                .and_modify(|existing_close_at| {
                    assert!(
                        existing_close_at == &close_at,
                        "Tumbling windower is not generating consistent boundaries"
                    )
                })
                .or_insert(close_at);
            vec![Ok(key)]
        }
    }

    fn drain_closed(&mut self, watermark: &DateTime<Utc>) -> Vec<WindowKey> {
        // TODO: Gosh I really want [`HashMap::drain_filter`].
        let mut future_close_times = HashMap::new();
        let mut closed_ids = Vec::new();

        for (id, close_at) in self.close_times.iter() {
            if close_at < watermark {
                closed_ids.push(*id);
            } else {
                future_close_times.insert(*id, *close_at);
            }
        }

        self.close_times = future_close_times;
        closed_ids
    }

    fn is_empty(&self) -> bool {
        self.close_times.is_empty()
    }

    fn next_close(&self) -> Option<DateTime<Utc>> {
        self.close_times.values().cloned().min()
    }

    fn snapshot(&self) -> StateBytes {
        StateBytes::ser::<HashMap<WindowKey, DateTime<Utc>>>(&self.close_times)
    }
}