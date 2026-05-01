from pathlib import Path


FALLBACK_DASHBOARD_TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>代理控制台</title>
  <style>
    body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 0; padding: 24px; background: #f8fafc; color: #17212d; }
    main { max-width: 760px; margin: 0 auto; background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px; }
    code { background: #eef2f7; padding: 2px 6px; border-radius: 6px; }
  </style>
</head>
<body>
  <main>
    <h1>代理控制台</h1>
    <p>未找到外部 <code>frontend/dashboard.html</code>，但代理服务已运行。</p>
    <p>接口入口：<code>http://127.0.0.1:{{ port }}/v1</code></p>
  </main>
</body>
</html>
""".strip()


def load_dashboard_template(project_root: Path, logger) -> str:
    template_path = project_root / "frontend" / "dashboard.html"
    if not template_path.exists():
        return FALLBACK_DASHBOARD_TEMPLATE

    try:
        return template_path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "dashboard_template_load_failed path=%s error=%s",
            template_path,
            str(exc),
        )
    return FALLBACK_DASHBOARD_TEMPLATE
