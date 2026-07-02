use std::collections::{BTreeMap, HashMap, HashSet};

use crate::models::{CountItem, SlotSummary, WorkInterval};

pub fn build_prediction(summary: &SlotSummary, history: &[WorkInterval]) -> (String, Vec<String>) {
    if summary.sample_count == 0 || summary.away_count >= summary.sample_count {
        return (
            "離席 / 不明".to_string(),
            vec![
                "休憩 / 離席".to_string(),
                "スリープ復帰直後 / 不明".to_string(),
                "作業内容を入力".to_string(),
            ],
        );
    }

    let current_features = summary_features(summary);
    let mut scored: Vec<(f64, String)> = history
        .iter()
        .filter_map(|interval| interval.confirmed_text.clone().map(|text| (interval, text)))
        .filter(|(_, text)| !text.trim().is_empty())
        .map(|(interval, text)| {
            let score = similarity(&current_features, &summary_features(&interval.summary));
            (score, text)
        })
        .filter(|(score, _)| *score > 0.0)
        .collect();

    scored.sort_by(|left, right| right.0.total_cmp(&left.0));

    let mut unique = HashSet::new();
    let mut ranked_history = Vec::new();

    for (score, text) in scored {
        if score < 0.15 {
            continue;
        }

        if unique.insert(text.clone()) {
            ranked_history.push(text);
        }
    }

    let primary = ranked_history
        .first()
        .cloned()
        .unwrap_or_else(|| fallback_prediction(summary));
    let mut alternatives = Vec::new();
    let mut alternative_set = HashSet::new();

    for text in ranked_history.into_iter().skip(1) {
        if text != primary && alternative_set.insert(text.clone()) {
            alternatives.push(text);
        }

        if alternatives.len() == 3 {
            break;
        }
    }

    for fallback in fallback_alternatives(summary) {
        if fallback != primary && alternative_set.insert(fallback.clone()) {
            alternatives.push(fallback);
        }

        if alternatives.len() == 3 {
            break;
        }
    }

    while alternatives.len() < 2 {
        let filler = if alternatives.is_empty() {
            "作業内容を入力".to_string()
        } else {
            format!("{}（別表現）", primary)
        };

        if filler != primary && alternative_set.insert(filler.clone()) {
            alternatives.push(filler);
        } else {
            break;
        }
    }

    (primary, alternatives)
}

fn fallback_prediction(summary: &SlotSummary) -> String {
    if let Some(title) = summary.top_titles.first() {
        if title.name != "除外" {
            return format!("「{}」を中心に作業", title.name);
        }
    }

    if let Some(process) = summary.top_processes.first() {
        if process.name != "除外" {
            return format!("{} を使った作業", process.name);
        }
    }

    "作業内容を入力".to_string()
}

fn fallback_alternatives(summary: &SlotSummary) -> Vec<String> {
    let mut values = Vec::new();

    if let Some(process) = summary.top_processes.first() {
        if process.name != "除外" {
            values.push(format!("{} を使った作業", process.name));
        }
    }

    if let Some(title) = summary.top_titles.first() {
        if title.name != "除外" {
            values.push(format!("「{}」の確認や編集", title.name));
        }
    }

    if let Some(token) = summary.top_title_tokens.first() {
        values.push(format!("{} 関連の作業", token.name));
    }

    values.push("作業内容を入力".to_string());

    let mut unique = HashSet::new();
    values
        .into_iter()
        .filter(|value| unique.insert(value.clone()))
        .collect()
}

fn summary_features(summary: &SlotSummary) -> BTreeMap<String, f64> {
    let mut features = BTreeMap::new();
    let total = summary.sample_count.max(1) as f64;

    add_weighted(&mut features, "process", &summary.top_processes, total, 2.0);
    add_weighted(&mut features, "title", &summary.top_titles, total, 1.5);
    add_weighted(
        &mut features,
        "token",
        &summary.top_title_tokens,
        total,
        1.0,
    );

    features
}

fn add_weighted(
    features: &mut BTreeMap<String, f64>,
    prefix: &str,
    items: &[CountItem],
    total: f64,
    multiplier: f64,
) {
    for item in items {
        features.insert(
            format!("{}:{}", prefix, item.name.to_lowercase()),
            (item.count as f64 / total) * multiplier,
        );
    }
}

fn similarity(left: &BTreeMap<String, f64>, right: &BTreeMap<String, f64>) -> f64 {
    let right_lookup: HashMap<&String, &f64> = right.iter().collect();
    left.iter()
        .filter_map(|(key, left_weight)| {
            right_lookup
                .get(key)
                .map(|right_weight| left_weight.min(**right_weight))
        })
        .sum()
}
