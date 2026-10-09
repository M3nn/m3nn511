"""اختبار تسجيل الدخول مباشرة عبر Flask test client."""
from app import create_app
from app.extensions import db
from app.models import User

app = create_app()
with app.app_context():
    user = db.session.query(User).filter_by(username="editor").first()
    if user:
        print(f"User found: {user.username}, role: {user.role}")
        print(f"Password check: {user.check_password('editor123')}")
    else:
        print("User not found")

# Test with test client
with app.test_client() as client:
    # Get login page
    resp = client.get("/auth/login")
    print(f"GET /auth/login: {resp.status_code}")
    
    # Extract CSRF token
    import re
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', resp.get_data(as_text=True))
    if csrf_match:
        csrf_token = csrf_match.group(1)
        print(f"CSRF token: {csrf_token[:50]}...")
        
        # POST login
        resp = client.post("/auth/login", data={
            "username": "editor",
            "password": "editor123",
            "csrf_token": csrf_token
        }, follow_redirects=False)
        print(f"POST /auth/login: {resp.status_code}")
        print(f"Location: {resp.headers.get('Location')}")
        print(f"Session cookie: {resp.headers.get('Set-Cookie')}")
    else:
        print("No CSRF token found")