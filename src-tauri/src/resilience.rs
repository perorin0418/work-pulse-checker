use std::{
    panic::{catch_unwind, AssertUnwindSafe},
    sync::{
        atomic::{AtomicI64, AtomicU64, Ordering},
        Arc,
    },
    thread,
    time::Duration,
};

/// ワーカー1ティック分の処理をパニックから隔離する。
/// パニックでスレッドごと死ぬと、プロセスは生きたまま監視だけ静かに止まるため。
pub fn guarded<F: FnOnce()>(label: &str, body: F) {
    if catch_unwind(AssertUnwindSafe(body)).is_err() {
        log::error!("worker tick panicked: {label}");
    }
}

/// 最後のティックからの経過が閾値を超えたか。閾値ちょうどはまだ停止とみなさない。
pub fn is_stale(last_tick: i64, now: i64, threshold_secs: i64) -> bool {
    now - last_tick > threshold_secs
}

/// ウォッチドッグとワーカーが共有する、ワーカー1本ぶんの状態。
pub struct WorkerPulse {
    pub last_tick: AtomicI64,
    pub generation: AtomicU64,
}

impl WorkerPulse {
    pub fn new(now: i64) -> Self {
        Self {
            last_tick: AtomicI64::new(now),
            generation: AtomicU64::new(0),
        }
    }
}

/// 世代番号が進むまでループし、1ティックごとに last_tick を更新する。
/// ハングした古いスレッドが後から復帰しても二重に動かないよう、
/// ループ先頭で自分の世代を確認して不一致なら抜ける。
pub fn run_worker_loop<F>(
    pulse: Arc<WorkerPulse>,
    my_generation: u64,
    label: &str,
    interval: Duration,
    now_secs: fn() -> i64,
    mut body: F,
) where
    F: FnMut(),
{
    loop {
        if pulse.generation.load(Ordering::SeqCst) != my_generation {
            return;
        }

        guarded(label, &mut body);
        pulse.last_tick.store(now_secs(), Ordering::SeqCst);
        thread::sleep(interval);
    }
}

#[cfg(test)]
mod tests {
    use std::{
        sync::{
            atomic::{AtomicU64, Ordering},
            Arc,
        },
        time::Duration,
    };

    use super::{guarded, is_stale, run_worker_loop, WorkerPulse};

    #[test]
    fn guarded_swallows_a_panic_and_returns_to_the_caller() {
        let mut ran = false;

        guarded("test", || {
            ran = true;
            panic!("boom");
        });

        assert!(ran);
    }

    #[test]
    fn guarded_runs_the_body_when_it_does_not_panic() {
        let mut ran = false;

        guarded("test", || ran = true);

        assert!(ran);
    }

    #[test]
    fn is_stale_is_false_exactly_at_the_threshold() {
        assert!(!is_stale(0, 90, 90));
    }

    #[test]
    fn is_stale_is_true_past_the_threshold() {
        assert!(is_stale(0, 91, 90));
    }

    #[test]
    fn worker_loop_exits_when_its_generation_is_superseded() {
        let pulse = Arc::new(WorkerPulse::new(0));
        let calls = Arc::new(AtomicU64::new(0));
        let body_pulse = pulse.clone();
        let body_calls = calls.clone();

        run_worker_loop(
            pulse.clone(),
            0,
            "test",
            Duration::from_millis(0),
            || 42,
            move || {
                if body_calls.fetch_add(1, Ordering::SeqCst) == 2 {
                    body_pulse.generation.store(1, Ordering::SeqCst);
                }
            },
        );

        assert_eq!(calls.load(Ordering::SeqCst), 3);
        assert_eq!(pulse.last_tick.load(Ordering::SeqCst), 42);
    }

    #[test]
    fn worker_loop_does_not_run_at_all_when_already_superseded() {
        let pulse = Arc::new(WorkerPulse::new(0));
        pulse.generation.store(5, Ordering::SeqCst);
        let calls = Arc::new(AtomicU64::new(0));
        let body_calls = calls.clone();

        run_worker_loop(
            pulse,
            0,
            "test",
            Duration::from_millis(0),
            || 42,
            move || {
                body_calls.fetch_add(1, Ordering::SeqCst);
            },
        );

        assert_eq!(calls.load(Ordering::SeqCst), 0);
    }
}
