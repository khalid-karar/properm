"""Create the first admin: PROPERM_ADMIN_ID / PROPERM_ADMIN_PASSWORD, then run
   python -m app.seed"""
import os
from .main import app_from_env
from .models import User
from .deps import hash_pw

if __name__ == "__main__":
    app = app_from_env()
    sid, pw = os.environ.get("PROPERM_ADMIN_ID", "admin"), os.environ.get("PROPERM_ADMIN_PASSWORD")
    if not pw or len(pw) < 8:
        raise SystemExit("Set PROPERM_ADMIN_PASSWORD (min 8 chars)")
    with app.state.Session() as db:
        if db.query(User).filter_by(staff_id=sid).first():
            raise SystemExit("Admin already exists")
        db.add(User(staff_id=sid, full_name="Administrator", role="ADMIN", password_hash=hash_pw(pw)))
        db.commit()
    print(f"Admin '{sid}' created")
