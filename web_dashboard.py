"""FastAPI веб-дашборд для бота-агрегатора вакансий."""

import sys
import os

try:
    # Добавляем текущую папку в PYTHONPATH, чтобы работали импорты app.* при прямом запуске
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    import secrets
    import base64
    from datetime import datetime, timedelta, timezone
    from collections import Counter
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse
    from starlette.middleware.base import BaseHTTPMiddleware
    from sqlalchemy import select, func
    from app.database import engine, Base, async_session
    from app.services.job_service import JobService
    from app.services.channel_rating import get_channel_ratings
    from app.utils.categorizer import get_category_label
    from app.utils.resume_parser import SKILLS_DATABASE
    from app.models.job import Job
    from app.models.user import User
    from app.models.stats import ParserStats
    from app.config import settings

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: создание таблиц
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield
        # Shutdown logic here if needed

    app = FastAPI(title="Job Aggregator Dashboard", version="2.0", lifespan=lifespan)

    # === Basic Auth Middleware ===
    class BasicAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Публичные эндпоинты
            if request.url.path in ["/", "/health", "/favicon.ico"]:
                return await call_next(request)

            # Статика и API могут требовать защиты, но для простоты /dashboard - главная цель
            auth = request.headers.get("Authorization")
            if auth and auth.startswith("Basic "):
                try:
                    scheme, credentials = auth.split(" ", 1)
                    decoded = base64.b64decode(credentials).decode("utf-8")
                    username, password = decoded.split(":", 1)
                    if secrets.compare_digest(
                        username, settings.DASHBOARD_USER
                    ) and secrets.compare_digest(password, settings.DASHBOARD_PASS):
                        return await call_next(request)
                except Exception as e:
                    print(f"Auth error: {e}")

            return HTMLResponse(
                content="🔒 Требуется авторизация для доступа к админ-панели",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Job Aggregator Admin"'},
            )

    app.add_middleware(BasicAuthMiddleware)

except Exception:
    import traceback

    print("=" * 50)
    print("КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ ДАШБОРДА:")
    print("=" * 50)
    traceback.print_exc()
    print("=" * 50)
    input("Нажмите Enter для выхода...")
    sys.exit(1)

HTML_LANDING = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="ArBOT Agregator — умный Telegram-бот для ИТ-специалистов. Поиск вакансий (Habr, hh.ru, TG), AI-анализ резюме, автогенерация сопроводительных писем и тестовые собеседования.">
    <meta name="keywords" content="IT вакансии, Telegram бот вакансии, AI для работы, поиск работы программисту, Python, React, сопроводительное письмо AI">
    <title>Найти IT-работу с ИИ | ArBOT Agregator</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', system-ui, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            line-height: 1.6;
            overflow-x: hidden;
        }}
        ::selection {{ background: #818cf8; color: #fff; }}

        .hero {{
            position: relative;
            padding: 100px 20px 80px;
            text-align: center;
            overflow: hidden;
        }}
        .hero::before {{
            content: '';
            position: absolute;
            top: -20%; left: 50%;
            transform: translateX(-50%);
            width: 800px; height: 800px;
            background: radial-gradient(circle, rgba(99,102,241,0.2) 0%, rgba(15,23,42,0) 70%);
            z-index: 0;
            pointer-events: none;
        }}

        .container {{
            max-width: 1100px;
            margin: 0 auto;
            position: relative;
            z-index: 10;
        }}

        h1 {{
            font-size: clamp(2.5rem, 5vw, 4rem);
            font-weight: 800;
            line-height: 1.1;
            margin-bottom: 24px;
            letter-spacing: -0.02em;
        }}
        .text-gradient {{
            background: linear-gradient(135deg, #a5b4fc 0%, #818cf8 50%, #c084fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: inline-block;
        }}
        .subtitle {{
            font-size: clamp(1.1rem, 2vw, 1.3rem);
            color: #94a3b8;
            max-width: 700px;
            margin: 0 auto 40px;
        }}

        .cta-button {{
            display: inline-flex;
            align-items: center;
            gap: 12px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            color: #fff;
            padding: 18px 40px;
            border-radius: 999px;
            font-size: 1.1rem;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.4);
        }}
        .cta-button:hover {{
            transform: translateY(-3px) scale(1.02);
            box-shadow: 0 20px 35px -5px rgba(99, 102, 241, 0.5);
        }}
        .tg-icon {{ width: 24px; height: 24px; fill: currentColor; }}

        .stats-wrap {{
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 24px;
            margin-top: 60px;
        }}
        .stat-box {{
            background: rgba(30, 41, 59, 0.6);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            padding: 24px 32px;
            border-radius: 20px;
            min-width: 220px;
            text-align: center;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        .stat-val {{
            font-size: 2.2rem;
            font-weight: 700;
            color: #fff;
            margin-bottom: 4px;
        }}
        .stat-label {{
            color: #94a3b8;
            font-weight: 500;
            font-size: 0.95rem;
        }}

        .features {{
            padding: 80px 20px;
            background: #0f172a;
        }}
        .features-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 30px;
            max-width: 1100px;
            margin: 0 auto;
        }}
        .feature-card {{
            background: #1e293b;
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 24px;
            padding: 32px;
            transition: transform 0.2s;
        }}
        .feature-card:hover {{ transform: translateY(-5px); border-color: rgba(99,102,241,0.3); }}
        .feature-icon {{
            font-size: 2.5rem;
            margin-bottom: 20px;
            display: inline-block;
            background: rgba(99,102,241,0.1);
            padding: 16px;
            border-radius: 16px;
        }}
        .feature-title {{ font-size: 1.3rem; margin-bottom: 12px; color: #f8fafc; font-weight: 600; }}
        .feature-desc {{ color: #94a3b8; font-size: 1rem; }}

        footer {{
            text-align: center;
            padding: 40px 20px;
            border-top: 1px solid rgba(255,255,255,0.05);
            color: #64748b;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>

    <section class="hero">
        <div class="container">
            <h1>Умный поиск IT-вакансий<br><span class="text-gradient">на базе Нейросетей</span></h1>
            <p class="subtitle">
                Больше никаких ручных откликов. Бот агрегирует вакансии из 5 источников, 
                пишет продающие Cover Letters и проводит мок-интервью в Telegram.
            </p>
            
            <a href="https://t.me/arbot_vacancies_bot" class="cta-button" target="_blank" rel="noopener">
                <svg class="tg-icon" viewBox="0 0 24 24">
                    <path d="M12 0c-6.627 0-12 5.373-12 12s5.373 12 12 12 12-5.373 12-12-5.373-12-12-12zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.446 1.394c-.14.18-.357.295-.6.295-.002 0-.003 0-.005 0l.213-3.054 5.56-5.022c.24-.213-.054-.334-.373-.121l-6.869 4.326-2.96-.924c-.64-.203-.658-.64.135-.954l11.566-4.458c.538-.196 1.006.128.832.94z"/>
                </svg>
                Запустить в Telegram
            </a>

            <div class="stats-wrap">
                <div class="stat-box">
                    <div class="stat-val">{total_jobs}</div>
                    <div class="stat-label">Свежих вакансий</div>
                </div>
                <div class="stat-box">
                    <div class="stat-val">5</div>
                    <div class="stat-label">IT-Источников</div>
                </div>
                <div class="stat-box">
                    <div class="stat-val">{total_users}</div>
                    <div class="stat-label">Кандидатов уже с нами</div>
                </div>
            </div>
        </div>
    </section>

    <section class="features">
        <div class="features-grid">
            <div class="feature-card">
                <div class="feature-icon">⚡</div>
                <h3 class="feature-title">Мгновенные уведомления</h3>
                <p class="feature-desc">Узнавайте о релевантных вакансиях с Habr, hh.ru и закрытых Telegram-каналов быстрее конкурентов.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🤖</div>
                <h3 class="feature-title">Генератор Cover Letter</h3>
                <p class="feature-desc">Нейросеть пишет уникальное сопроводительное письмо под каждую конкретную вакансию на основе вашего стека.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">💬</div>
                <h3 class="feature-title">Чат с вакансией</h3>
                <p class="feature-desc">Лень читать портянку текста? Просто спросите у ИИ: "Тут есть удаленка?" или "Какой размер вилки?".</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🎯</div>
                <h3 class="feature-title">AI-Собеседование</h3>
                <p class="feature-desc">Потренируйтесь отвечать на технические вопросы перед реальным интервью в формате интерактивного диалога.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🚫</div>
                <h3 class="feature-title">Анти-спам фильтр</h3>
                <p class="feature-desc">Укажите стоп-слова (например: 1С, офис), и бот навсегда скроет нерелевантный мусор из ленты.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">📊</div>
                <h3 class="feature-title">Метчинг навыков</h3>
                <p class="feature-desc">Алгоритм оценивает ваш скиллсет (Python, Docker, AWS) и подсвечивает вакансии с совпадением 80%+.</p>
            </div>
        </div>
    </section>

    <footer>
        <div class="container">
            &copy; 2026 ArBOT Agregator. Сделано для IT-сообщества.
        </div>
    </footer>

    <script>
        // Автоматическое обновление статистики каждые 60 секунд
        setTimeout(() => {{
            window.location.reload();
        }}, 60000);
    </script>
</body>
</html>"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Aggregator — Дашборд</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', system-ui, sans-serif;
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            color: #e0e0e0;
            min-height: 100vh;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}

        header {{
            text-align: center;
            padding: 40px 0 20px;
        }}
        header h1 {{
            font-size: 2.5em;
            background: linear-gradient(90deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        header p {{ color: #999; font-size: 1.1em; }}
        .subtitle {{ color: #667eea; font-size: 0.9em; margin-top: 5px; }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 16px;
            margin: 25px 0;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 22px;
            text-align: center;
            backdrop-filter: blur(10px);
            transition: transform 0.2s;
        }}
        .stat-card:hover {{ transform: translateY(-4px); }}
        .stat-card .number {{
            font-size: 2.2em;
            font-weight: 700;
            background: linear-gradient(90deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .stat-card .label {{ color: #999; margin-top: 4px; font-size: 0.9em; }}

        .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin: 30px 0; }}
        @media (max-width: 768px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

        .section {{ margin: 30px 0; }}
        .section h2 {{
            font-size: 1.4em;
            margin-bottom: 16px;
            color: #fff;
        }}

        .card {{
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            padding: 20px;
        }}

        .skill-row {{
            display: flex;
            align-items: center;
            margin: 6px 0;
            gap: 10px;
        }}
        .skill-row .rank {{ width: 24px; text-align: right; color: #999; font-size: 0.85em; }}
        .skill-row .name {{ width: 110px; font-weight: 500; font-size: 0.95em; }}
        .skill-row .bar-wrap {{
            flex: 1;
            height: 6px;
            background: rgba(255,255,255,0.08);
            border-radius: 3px;
            overflow: hidden;
        }}
        .skill-row .bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 3px;
        }}
        .skill-row .count {{ width: 35px; text-align: right; color: #999; font-size: 0.85em; }}

        .jobs-table {{
            width: 100%;
            border-collapse: collapse;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            overflow: hidden;
        }}
        .jobs-table th {{
            background: rgba(102,126,234,0.2);
            padding: 10px 14px;
            text-align: left;
            font-weight: 600;
            color: #b0b0f0;
            font-size: 0.9em;
        }}
        .jobs-table td {{
            padding: 10px 14px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 0.9em;
        }}
        .jobs-table tr:hover td {{ background: rgba(255,255,255,0.03); }}
        .jobs-table a {{ color: #667eea; text-decoration: none; }}
        .jobs-table a:hover {{ text-decoration: underline; }}

        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 8px;
            font-size: 0.75em;
            background: rgba(102,126,234,0.2);
            color: #b0b0f0;
        }}
        .badge-src {{
            background: rgba(118,75,162,0.2);
            color: #c0a0f0;
        }}

        .rating-bar {{
            display: flex;
            align-items: center;
            margin: 6px 0;
            padding: 8px 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
        }}
        .rating-bar .name {{ flex: 1; font-weight: 500; font-size: 0.9em; }}
        .rating-bar .bar {{
            flex: 2;
            height: 7px;
            background: rgba(255,255,255,0.08);
            border-radius: 4px;
            margin: 0 12px;
            overflow: hidden;
        }}
        .rating-bar .bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 4px;
        }}
        .rating-bar .count {{ color: #999; min-width: 55px; text-align: right; font-size: 0.85em; }}

        .new-badge {{
            display: inline-block;
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 0.7em;
            background: rgba(118,204,131,0.2);
            color: #76cc83;
            margin-left: 6px;
        }}

        /* Parser Health Cards */
        .health-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .health-card {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 18px;
            padding: 20px;
            display: flex;
            align-items: center;
            gap: 15px;
            transition: 0.3s;
        }}
        .health-card:hover {{ background: rgba(255, 255, 255, 0.08); transform: translateY(-2px); }}
        .status-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
        .status-ok {{ background: #10b981; box-shadow: 0 0 10px #10b981; }}
        .status-error {{ background: #ef4444; box-shadow: 0 0 10px #ef4444; }}
        .status-ban {{ background: #f59e0b; box-shadow: 0 0 10px #f59e0b; }}
        
        .health-info {{ flex: 1; }}
        .health-name {{ font-weight: 700; font-size: 1.1em; margin-bottom: 2px; }}
        .health-meta {{ font-size: 0.85em; color: #94a3b8; }}
        .health-stats {{ font-size: 0.9em; margin-top: 8px; color: #e2e8f0; }}
        .health-error {{ font-size: 0.8em; color: #fca5a5; margin-top: 5px; font-style: italic; }}

        footer {{
            text-align: center;
            padding: 30px 0;
            color: #555;
            font-size: 0.85em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔔 Job Aggregator</h1>
            <p>Дашборд бота-агрегатора вакансий</p>
            <div class="subtitle">5 источников • TG · hh.ru · Habr · Kwork · FL.ru</div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="number">{total_jobs}</div>
                <div class="label">Всего вакансий</div>
            </div>
            <div class="stat-card">
                <div class="number">{new_24h}</div>
                <div class="label">Новых за 24ч</div>
            </div>
            <div class="stat-card">
                <div class="number">{total_users}</div>
                <div class="label">Пользователей</div>
            </div>
            <div class="stat-card">
                <div class="number">{active_parsers}</div>
                <div class="label">Работает парсеров</div>
            </div>
        </div>

        <div class="section">
            <h2>🛡 Состояние парсеров (Health)</h2>
            <div class="health-grid">
                {health_html}
            </div>
        </div>

        <div class="two-col">
            <div class="section">
                <h2>🏆 Топ навыков</h2>
                <div class="card chart-container">
                    <canvas id="skillsChart"></canvas>
                </div>
            </div>
            <div class="section">
                <h2>📊 Источники и Платформы</h2>
                <div class="card chart-container">
                    <canvas id="sourcesChart"></canvas>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>📋 Последние вакансии</h2>
            <table class="jobs-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Вакансия</th>
                        <th>Категория</th>
                        <th>Источник</th>
                        <th>Ссылка</th>
                    </tr>
                </thead>
                <tbody>
                    {jobs_html}
                </tbody>
            </table>
        </div>

        <footer>
            Job Aggregator Bot &copy; 2026 | Обновлено: {updated_at}
        </footer>
    </div>

    <script>
        // Глобальные настройки для темной темы
        Chart.defaults.color = '#9ca3af';
        Chart.defaults.font.family = "'Inter', sans-serif";
        
        const skillsData = {skills_json};
        const sourcesData = {sources_json};

        // Топ навыков (Горизонтальный Bar Chart)
        const ctxSkills = document.getElementById('skillsChart').getContext('2d');
        new Chart(ctxSkills, {{
            type: 'bar',
            data: {{
                labels: skillsData.map(s => s.name),
                datasets: [{{
                    label: 'Упоминаний',
                    data: skillsData.map(s => s.count),
                    backgroundColor: 'rgba(102, 126, 234, 0.7)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 1,
                    borderRadius: 4
                }}]
            }},
            options: {{
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }} }},
                    y: {{ grid: {{ display: false }} }}
                }}
            }}
        }});

        // Источники (Doughnut Chart)
        const ctxSources = document.getElementById('sourcesChart').getContext('2d');
        new Chart(ctxSources, {{
            type: 'doughnut',
            data: {{
                labels: sourcesData.map(s => s.name),
                datasets: [{{
                    data: sourcesData.map(s => s.count),
                    backgroundColor: [
                        '#667eea', '#764ba2', '#ff6b6b', '#4ecdc4',
                        '#ffe66d', '#118ab2', '#06d6a0'
                    ],
                    borderWidth: 2,
                    borderColor: '#24243e'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ position: 'right' }}
                }},
                cutout: '70%'
            }}
        }});
        // Автоматическое обновление данных на дашборде каждые 60 секунд
        setTimeout(() => {{
            window.location.reload();
        }}, 60000);
    </script>
</body>
</html>"""


# Обработчики событий (Deprecated in 2.0, moved to lifespan)
# @app.on_event("startup")


@app.get("/", response_class=HTMLResponse)
async def landing():
    async with async_session() as session:
        job_service = JobService(session)
        total = await job_service.count_jobs()
        users_count = (await session.execute(select(func.count(User.id)))).scalar_one()

    html = HTML_LANDING.format(total_jobs=total, total_users=users_count)
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    async with async_session() as session:
        job_service = JobService(session)
        total = await job_service.count_jobs()
        await job_service.count_by_source()
        await job_service.count_by_category()
        jobs = await job_service.get_latest_jobs(limit=30)

        # Новые за 24ч
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        new_24h_result = await session.execute(
            select(func.count(Job.id)).where(Job.created_at >= cutoff)
        )
        new_24h = new_24h_result.scalar_one()

        # Пользователи
        users_count = (await session.execute(select(func.count(User.id)))).scalar_one()

        # Парсеры
        parser_stats_raw = await session.execute(
            select(ParserStats).order_by(ParserStats.parser_name)
        )
        parser_stats = parser_stats_raw.scalars().all()
        active_parsers_count = sum(1 for s in parser_stats if s.status == "OK")

        # Топ навыков
        all_jobs = await session.execute(select(Job.title, Job.description).limit(500))
        all_jobs_list = all_jobs.all()

    ratings = await get_channel_ratings()
    max((r["total"] for r in ratings), default=1)

    # Подготовка данных для JS (Топ навыков)
    skill_counter = Counter()
    for title, desc in all_jobs_list:
        text = f"{title} {desc or ''}".lower()
        for skill, patterns in SKILLS_DATABASE.items():
            for p in patterns:
                if p in text:
                    skill_counter[skill] += 1
                    break

    top_skills = skill_counter.most_common(10)
    import json

    skills_json = json.dumps([{"name": k, "count": v} for k, v in top_skills])

    # Подготовка данных для JS (Источники)
    sources_json = json.dumps(
        [{"name": r["source"], "count": r["total"]} for r in ratings]
    )

    # Карточки здоровья парсеров
    health_html = ""
    for s in parser_stats:
        dot_class = (
            "status-ok"
            if s.status == "OK"
            else ("status-ban" if s.status == "BAN" else "status-error")
        )
        status_text = (
            "Работает"
            if s.status == "OK"
            else ("Забанен" if s.status == "BAN" else "Ошибка")
        )
        err_html = (
            f'<div class="health-error">{s.last_error[:60]}...</div>'
            if s.last_error
            else ""
        )

        health_html += f"""
        <div class="health-card">
            <div class="status-dot {dot_class}"></div>
            <div class="health-info">
                <div class="health-name">{s.parser_name}</div>
                <div class="health-meta">{status_text} • Обновлено в {s.updated_at.strftime("%H:%M")}</div>
                <div class="health-stats">📦 Найдено сегодня: <b>{s.total_today}</b></div>
                {err_html}
            </div>
        </div>"""

    # Таблица вакансий
    src_icons = {
        "hh.ru": "🏢",
        "habr.career": "💻",
        "kwork.ru": "🟠",
        "fl.ru": "🔵",
        "superjob.ru": "💼",
        "rabota.ru": "💎",
    }
    cutoff_24 = datetime.now(timezone.utc) - timedelta(hours=24)
    jobs_html = ""
    for i, job in enumerate(jobs, 1):
        cat = get_category_label(job.category) if job.category else "—"
        src = job.source or "—"
        icon = src_icons.get(src, "📱")
        link = f'<a href="{job.link}" target="_blank">Открыть</a>' if job.link else "—"
        new = (
            '<span class="new-badge">NEW</span>'
            if job.created_at and job.created_at > cutoff_24
            else ""
        )
        jobs_html += f"""
        <tr>
            <td>{i}</td>
            <td>{job.title[:55]}{new}</td>
            <td><span class="badge">{cat}</span></td>
            <td><span class="badge badge-src">{icon} {src}</span></td>
            <td>{link}</td>
        </tr>"""

    html = HTML_TEMPLATE.format(
        total_jobs=total,
        new_24h=new_24h,
        active_parsers=active_parsers_count,
        total_users=users_count,
        health_html=health_html or "<p>Нет данных о парсерах</p>",
        skills_json=skills_json,
        sources_json=sources_json,
        jobs_html=jobs_html or "<tr><td colspan='5'>Нет вакансий</td></tr>",
        updated_at=datetime.now().strftime("%d.%m.%Y %H:%M"),
    )
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/jobs")
async def api_jobs(page: int = 0, per_page: int = 20):
    async with async_session() as session:
        job_service = JobService(session)
        total = await job_service.count_jobs()
        jobs = await job_service.get_jobs_page(page=page, per_page=per_page)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "jobs": [
            {
                "id": j.id,
                "title": j.title,
                "description": j.description[:300] if j.description else "",
                "link": j.link,
                "source": j.source,
                "category": j.category,
                "created_at": str(j.created_at),
            }
            for j in jobs
        ],
    }


@app.get("/api/stats")
async def api_stats():
    async with async_session() as session:
        job_service = JobService(session)
        total = await job_service.count_jobs()
        by_source = await job_service.count_by_source()
        by_category = await job_service.count_by_category()

    ratings = await get_channel_ratings()

    return {
        "total_jobs": total,
        "by_source": by_source,
        "by_category": by_category,
        "channel_ratings": ratings,
    }


@app.get("/api/skills")
async def api_skills():
    """Топ навыков через API."""
    async with async_session() as session:
        result = await session.execute(select(Job.title, Job.description).limit(500))
        jobs = result.all()

    skill_counter = Counter()
    for title, desc in jobs:
        text = f"{title} {desc or ''}".lower()
        for skill, patterns in SKILLS_DATABASE.items():
            for p in patterns:
                if p in text:
                    skill_counter[skill] += 1
                    break

    return {
        "skills": [{"name": s, "count": c} for s, c in skill_counter.most_common(20)]
    }


@app.get("/health")
async def health_check():
    try:
        async with async_session() as session:
            job_service = JobService(session)
            total = await job_service.count_jobs()
        return {
            "status": "healthy",
            "total_jobs": total,
            "timestamp": str(datetime.now()),
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def _get_local_ip():
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    import uvicorn
    import sys

    try:
        local_ip = _get_local_ip()
        print("=" * 60)
        print("          ЗАПУСК WEB-ДАШБОРДА          ")
        print("=" * 60)
        print("👉 Лендинг (открытый): http://127.0.0.1:8085")
        print("🔒 Админка (с паролем): http://127.0.0.1:8085/dashboard")
        print(f"📱 Доступ с ТЕЛЕФОНА (Wi-Fi): http://{local_ip}:8085")
        print("=" * 60)
        uvicorn.run(app, host="0.0.0.0", port=8085)
    except Exception as e:
        print(f"Ошибка при запуске: {e}")
        input("Нажмите Enter для выхода...")
