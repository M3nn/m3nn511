"""اختبار مسارات AI بعد تسجيل الدخول."""
from app import create_app
from app.extensions import db
from app.models import User, Article, ArticleStatus, Task, TaskStatus, Priority
import datetime as dt

app = create_app()
with app.app_context():
    # Get an article ID for testing AI summary
    article = db.session.query(Article).filter_by(status=ArticleStatus.PUBLISHED).first()
    print(f"Test article: {article.id} - {article.title[:50]}")
    
with app.test_client() as client:
    # Login as editor
    resp = client.get("/auth/login")
    import re
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', resp.get_data(as_text=True))
    csrf_token = csrf_match.group(1)
    
    resp = client.post("/auth/login", data={
        "username": "editor",
        "password": "editor123",
        "csrf_token": csrf_token
    }, follow_redirects=True)
    print(f"Login: {resp.status_code}")
    
    # Test AI-1: summarize article
    print("\n=== AI-1: Article Summary ===")
    resp = client.post(f"/editor/articles/{article.id}/ai-summary",
                       headers={"HX-Request": "true"})
    print(f"POST /editor/articles/{article.id}/ai-summary: {resp.status_code}")
    print(f"Response: {resp.get_data(as_text=True)[:300]}")
    
    # Test AI-2: suggest tasks
    print("\n=== AI-2: Task Suggestions ===")
    resp = client.get("/tasks/suggest")
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', resp.get_data(as_text=True))
    csrf_token = csrf_match.group(1)
    
    resp = client.post("/tasks/suggest", data={
        "brief": "كتابة تقرير عن مباراة النصر القادمة",
        "csrf_token": csrf_token
    }, headers={"HX-Request": "true"})
    print(f"POST /tasks/suggest: {resp.status_code}")
    print(f"Response: {resp.get_data(as_text=True)[:300]}")
    
    # Test /editor access
    print("\n=== Editor pages ===")
    resp = client.get("/editor")
    print(f"GET /editor: {resp.status_code}")
    
    resp = client.get("/editor/stats")
    print(f"GET /editor/stats: {resp.status_code}")
    
    # Test /tasks access
    resp = client.get("/tasks")
    print(f"GET /tasks: {resp.status_code}")
    
    # Logout
    resp = client.post("/auth/logout", follow_redirects=True)
    print(f"\nLogout: {resp.status_code}")