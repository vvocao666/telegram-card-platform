from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatusPanelSnapshot:
    service_state: str
    branch: str
    commit: str
    memory: str
    uptime: str
    ledger_exists: bool
    remote_label: str
    remote_enabled: bool
    worker_ok: bool
    worker_status: str
    worker_gpu: str
    worker_engine: str
    avg_remote_latency_ms: int
    last_success: str
    last_failed: str
    last_error: str
    current_provider: str
    ocrspace_available: bool
    remote_calls: int
    remote_success: int
    remote_failed: int
    fallback_count: int
    cache_hit_rate: str
    enhanced_rate: str
    image_count: int
    card_count: int
    pubg_count: int
    psn_count: int
    duplicate_count: int
    worker_cpu_status: str = "未启用"
    worker_gpu_tasks: int = 0
    worker_cpu_tasks: int = 0
    worker_gpu_avg_ms: int = 0
    worker_cpu_avg_ms: int = 0
    worker_queue_depth: int = 0
    worker_cache_hits: int = 0
    worker_conflicts: int = 0


def render_status_panel(snapshot: StatusPanelSnapshot) -> str:
    service_state = snapshot.service_state
    lines = [
        "━━━━━━━━━━━━━━",
        "📊 机器人状态",
        "━━━━━━━━━━━━━━",
        "",
        "🤖 阿里云机器人",
        f"状态：{'运行中' if service_state == 'active' else service_state}",
        "版本：v2.2-status-panel",
        f"服务：telegram-card-platform {service_state}{'/running' if service_state == 'active' else ''}",
        f"分支：{snapshot.branch}",
        f"Commit：{snapshot.commit}",
        f"内存：{snapshot.memory}",
        f"运行时间：{snapshot.uptime}",
        f"ledger.sqlite3：{'存在' if snapshot.ledger_exists else '缺失'}",
        "",
        f"🖥 {snapshot.remote_label}",
        f"启用：{'是' if snapshot.remote_enabled else '否'}",
        f"状态：{'在线' if snapshot.worker_ok else '离线'}",
        f"status：{snapshot.worker_status}",
        f"GPU：{snapshot.worker_gpu}",
        f"引擎：{snapshot.worker_engine}",
        f"平均延迟：{snapshot.avg_remote_latency_ms} ms",
        f"最近成功：{snapshot.last_success}",
        f"最近失败：{snapshot.last_failed}",
        f"最近错误：{snapshot.last_error}",
    ]
    lines.extend(
        [
            "",
            "【本地识别】",
            f"GPU：{'在线' if snapshot.worker_ok else '离线'}",
            f"CPU OCR：{snapshot.worker_cpu_status}",
            f"GPU Worker任务：{snapshot.worker_gpu_tasks}",
            f"CPU Worker任务：{snapshot.worker_cpu_tasks}",
            f"GPU 平均耗时：{snapshot.worker_gpu_avg_ms or '暂无'}{' ms' if snapshot.worker_gpu_avg_ms else ''}",
            f"CPU 平均耗时：{snapshot.worker_cpu_avg_ms or '暂无'}{' ms' if snapshot.worker_cpu_avg_ms else ''}",
            f"当前队列：{snapshot.worker_queue_depth}",
            f"Worker缓存命中：{snapshot.worker_cache_hits}",
            f"冲突复核：{snapshot.worker_conflicts}",
            "",
            "🔁 OCR 路由",
            f"Remote：{'已配置' if snapshot.remote_enabled else '未配置'}",
            f"当前主引擎：{snapshot.current_provider}",
            "备用引擎：OCR.space",
            f"OCR.space fallback：{'可用' if snapshot.ocrspace_available else '未配置'}",
            f"今日 Remote 调用：{snapshot.remote_calls}",
            f"成功：{snapshot.remote_success}",
            f"失败：{snapshot.remote_failed}",
            f"Fallback：{snapshot.fallback_count}",
            f"缓存命中率：{snapshot.cache_hit_rate}",
            f"OpenCV增强率：{snapshot.enhanced_rate}",
            "",
            "📦 今日识别",
            f"图片：{snapshot.image_count} 张",
            f"卡密：{snapshot.card_count} 个",
            f"PUBG卡密：{snapshot.pubg_count} 个",
            f"PSN卡密：{snapshot.psn_count} 个",
            f"重复：{snapshot.duplicate_count} 个",
            "",
            "━━━━━━━━━━━━━━",
        ]
    )
    return "\n".join(lines)
