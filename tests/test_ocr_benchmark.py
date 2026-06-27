from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass

import bot


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    raw_text: str
    expected_pubg: tuple[str, ...] = tuple()
    expected_psn: tuple[str, ...] = tuple()
    use_ordered_lines: bool = False


BENCHMARK_CASES = (
    BenchmarkCase(
        name="clear_pubg",
        raw_text="S07304-M6TT-TVG5-858NQ\nS07304-4VT2-49PP-T9TWM",
        expected_pubg=("S07304-M6TT-TVG5-858NQ", "S07304-4VT2-49PP-T9TWM"),
    ),
    BenchmarkCase(
        name="clear_psn",
        raw_text="FK4L-D7MP-2GQX\nN74H-KCGT-FDQA",
        expected_psn=("FK4L-D7MP-2GQX", "N74H-KCGT-FDQA"),
    ),
    BenchmarkCase(
        name="s07_any_prefix_pubg",
        raw_text="S07298-SF9Y-BEYJ-PXYHZ\nS07292-XTLV-W93R-5P55S",
        expected_pubg=("S07298-SF9Y-BEYJ-PXYHZ", "S07292-XTLV-W93R-5P55S"),
    ),
    BenchmarkCase(
        name="pubg_line_wrap",
        raw_text="卡号：S07304-94VF-NG88-\nKLQUE\n密码：\n卡号：S07304-UM3A-RHGF-\nSY5RQ",
        expected_pubg=("S07304-94VF-NG88-KLQUE", "S07304-UM3A-RHGF-SY5RQ"),
        use_ordered_lines=True,
    ),
    BenchmarkCase(
        name="compressed_incomplete_pubg",
        raw_text="S07304-94VF-NG88-\nJE\nS07304-UM3A-RHGF-\nSY5RQ",
        expected_pubg=("S07304-UM3A-RHGF-SY5RQ",),
        use_ordered_lines=True,
    ),
    BenchmarkCase(
        name="multi_card_image",
        raw_text="S07304-S7L2-74K4-W3KET\nS07304-P738-VC3Q-MPWDA\nS07304-5PH4-33CS-KATP6",
        expected_pubg=("S07304-S7L2-74K4-W3KET", "S07304-P738-VC3Q-MPWDA", "S07304-5PH4-33CS-KATP6"),
    ),
    BenchmarkCase(
        name="pubg_not_psn_substring",
        raw_text="S07304-KJDS-NPDD-NEUDY\nKJDS-NPDD-NEUD",
        expected_pubg=("S07304-KJDS-NPDD-NEUDY",),
    ),
    BenchmarkCase(
        name="psn_not_pubg",
        raw_text="PlayStation Network Card\nFK4L-D7MP-2GQX\nN74H-KCGT-FDQA",
        expected_psn=("FK4L-D7MP-2GQX", "N74H-KCGT-FDQA"),
    ),
    BenchmarkCase(
        name="no_card_image",
        raw_text="订单信息\n商品名称\n没有任何卡密",
    ),
)


def _parse_case(case: BenchmarkCase) -> tuple[tuple[str, ...], tuple[str, ...], bool, float]:
    start = time.perf_counter()
    if case.use_ordered_lines:
        lines = bot.ordered_ocr_text_lines(case.raw_text.splitlines())
        pubg, unresolved = bot.extract_cards_from_ordered_lines(lines)
    else:
        pubg = bot.extract_cards(case.raw_text)
        unresolved = False
    psn = bot.psn_ordered_for_image(case.raw_text, pubg)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return tuple(pubg), tuple(psn), unresolved, elapsed_ms


def test_ocr_benchmark_accuracy_and_latency(caplog):
    timings: list[float] = []
    pubg_total = 0
    psn_total = 0
    missing = 0
    false_positive = 0
    type_mix = 0

    with caplog.at_level(logging.INFO, logger="telegram-card-platform"):
        for case in BENCHMARK_CASES:
            pubg, psn, _unresolved, elapsed_ms = _parse_case(case)
            timings.append(elapsed_ms)
            pubg_total += len(case.expected_pubg)
            psn_total += len(case.expected_psn)
            missing += len(set(case.expected_pubg) - set(pubg))
            missing += len(set(case.expected_psn) - set(psn))
            false_positive += len(set(pubg) - set(case.expected_pubg))
            false_positive += len(set(psn) - set(case.expected_psn))
            if pubg and psn:
                type_mix += 1

            assert pubg == case.expected_pubg, case.name
            assert psn == case.expected_psn, case.name

        ordered = sorted(timings)
        p50 = statistics.median(ordered)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        bot.logger.info(
            "OCR BENCHMARK summary=cases:%s pubg:%s psn:%s missing:%s false_positive:%s type_mix:%s p50_ms:%.3f p95_ms:%.3f",
            len(BENCHMARK_CASES),
            pubg_total,
            psn_total,
            missing,
            false_positive,
            type_mix,
            p50,
            p95,
        )

    assert missing == 0
    assert false_positive == 0
    assert type_mix == 0
    assert max(timings) < 50
    assert "OCR BENCHMARK summary=" in caplog.text
