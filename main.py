import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

from fastapi import FastAPI, Depends, HTTPException, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from typing import Optional, Literal
from datetime import datetime, timedelta

from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship

from passlib.context import CryptContext
from jose import jwt, JWTError
from starlette.middleware.sessions import SessionMiddleware


# NEW: Load environment variables from .env file
load_dotenv()

# ----------------------------
# Config (Now loaded securely from environment variables)
# ----------------------------
SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
DATABASE_URL = os.environ.get("DATABASE_URL")

if SECRET_KEY is None:
    raise ValueError("SECRET_KEY is not set in the environment. Please create a .env file.")

# ----------------------------
# NEW: Logging Setup
# ----------------------------
# Get a logger instance
logger = logging.getLogger(__name__)

def setup_logging():
    """Configures the logging for the application."""
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # File handler that rotates logs, keeping 5 backups of 1MB each
    file_handler = RotatingFileHandler('app.log', maxBytes=1024*1024, backupCount=5)
    file_handler.setFormatter(log_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    
    # Get the root logger and add handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

# ----------------------------
# Database Setup
# ----------------------------
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# ... User and Todo models (keep them as they are)
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    todos = relationship("Todo", back_populates="owner", cascade="all, delete-orphan")

class Todo(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="todos")

Base.metadata.create_all(bind=engine)

# ... Password & JWT Helpers (keep them as they are)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

def get_password_hash(password):
    password_bytes = password.encode('utf-8')[:72]
    return pwd_context.hash(password_bytes)

def verify_password(plain_password, hashed_password):
    password_bytes = plain_password.encode('utf-8')[:72]
    return pwd_context.verify(password_bytes, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def _get_user_from_token(db: Session, token: Optional[str]):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: return None
        return db.query(User).filter(User.username == username).first()
    except JWTError:
        return None

def get_current_user_optional(request: Request, db: Session = Depends(lambda: next(get_db()))):
    token = request.cookies.get("access_token")
    return _get_user_from_token(db, token)

def get_current_user(request: Request, db: Session = Depends(lambda: next(get_db()))):
    user = get_current_user_optional(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return user

# ----------------------------
# App Setup
# ----------------------------
app = FastAPI(title="To-Do App", description="A simple task management application", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# NEW: Run the logging setup when the application starts
@app.on_event("startup")
async def startup_event():
    setup_logging()
    logger.info("Application startup complete.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
# ... Flash message helpers (keep them as they are)
def flash(request: Request, message: str, category: str = "info"):
    if "_messages" not in request.session: request.session["_messages"] = []
    request.session["_messages"].append({"message": message, "category": category})

def get_flashed_messages(request: Request):
    return request.session.pop("_messages") if "_messages" in request.session else []

templates.env.globals['get_flashed_messages'] = get_flashed_messages

# ----------------------------
# Routes (MODIFIED with logging)
# ----------------------------

# ... index route (no logging needed here)
@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    filter: Literal["all", "pending", "completed"] = "all"
):
    if isinstance(user, RedirectResponse): return user
    
    all_todos_query = db.query(Todo).filter(Todo.user_id == user.id)
    if filter == "pending": todos_query = all_todos_query.filter(Todo.completed == False)
    elif filter == "completed": todos_query = all_todos_query.filter(Todo.completed == True)
    else: todos_query = all_todos_query

    todos = todos_query.order_by(Todo.created_at.desc()).all()
    all_todos = all_todos_query.all()

    completed_count = sum(1 for todo in all_todos if todo.completed)
    pending_count = len(all_todos) - completed_count
    
    return templates.TemplateResponse("index.html", {
        "request": request, "todos": todos, "user": user,
        "completed_count": completed_count, "pending_count": pending_count,
        "total_count": len(all_todos), "current_filter": filter
    })


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    # ... (validation logic remains the same)
    if len(username) < 3:
        flash(request, "Username must be at least 3 characters long", "error")
        return templates.TemplateResponse("register.html", {"request": request}, status_code=400)
    if len(password) < 6:
        flash(request, "Password must be at least 6 characters long", "error")
        return templates.TemplateResponse("register.html", {"request": request}, status_code=400)
    if db.query(User).filter(User.username == username).first():
        flash(request, "Username already exists", "error")
        return templates.TemplateResponse("register.html", {"request": request}, status_code=400)
    
    user = User(username=username, hashed_password=get_password_hash(password))
    db.add(user)
    db.commit()
    
    logger.info(f"New user registered: '{username}'") # MODIFIED
    
    flash(request, "Registration successful! Please login.", "success")
    return RedirectResponse("/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        logger.warning(f"Failed login attempt for username: '{username}'") # MODIFIED
        flash(request, "Invalid username or password", "error")
        return templates.TemplateResponse("login.html", {"request": request}, status_code=401)
    
    access_token = create_access_token({"sub": user.username})
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite="lax")
    
    logger.info(f"User logged in successfully: '{username}'") # MODIFIED
    
    return response

# ... change_password route
@app.post("/change-password")
def change_password(request: Request, old_password: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # ... (validation logic)
    if isinstance(user, RedirectResponse): return user
    if not verify_password(old_password, user.hashed_password):
        flash(request, "Current password is incorrect", "error")
        return templates.TemplateResponse("change_password.html", {"request": request, "user": user}, status_code=400)
    
    # ... more validation
    
    db_user = db.query(User).filter(User.id == user.id).first()
    db_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    logger.info(f"User '{user.username}' changed their password successfully.") # MODIFIED
    
    flash(request, "Password changed successfully!", "success")
    return templates.TemplateResponse("change_password.html", {"request": request, "user": user})


@app.post("/add_todo")
def add_todo(request: Request, title: str = Form(...), description: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if isinstance(user, RedirectResponse): return user
    if not title.strip():
        flash(request, "Title cannot be empty", "error")
        return RedirectResponse("/", status_code=303)
    
    todo = Todo(title=title.strip(), description=description.strip(), user_id=user.id)
    db.add(todo)
    db.commit()
    
    logger.info(f"User '{user.username}' added a new task: '{title.strip()}' (ID: {todo.id})") # MODIFIED
    
    flash(request, "Task added successfully.", "success")
    return RedirectResponse("/?filter=pending", status_code=303)

@app.post("/toggle_todo/{todo_id}")
def toggle_todo(request: Request, todo_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if isinstance(user, RedirectResponse): return user
    todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == user.id).first()
    if not todo: raise HTTPException(status_code=404, detail="Todo not found")
    
    todo.completed = not todo.completed
    db.commit()

    status = "completed" if todo.completed else "pending"
    logger.info(f"User '{user.username}' changed status of task ID {todo_id} to '{status}'") # MODIFIED
    
    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=303)

@app.post("/delete_todo/{todo_id}")
def delete_todo(request: Request, todo_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if isinstance(user, RedirectResponse): return user
    todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == user.id).first()
    if not todo: raise HTTPException(status_code=404, detail="Todo not found")
    
    db.delete(todo)
    db.commit()

    logger.info(f"User '{user.username}' deleted task ID {todo_id}") # MODIFIED
    
    flash(request, "Task deleted.", "success")
    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=303)

# ... (rest of the routes like delete_all_completed, logout, health_check can remain as they are, or add logging if you wish)