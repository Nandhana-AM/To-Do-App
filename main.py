import os
# NEW: Import Literal for type hinting the filter options
from typing import Optional, Literal
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

load_dotenv()


# ----------------------------
# Config (Best Practice: Load from environment variables)
# ----------------------------
SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
DATABASE_URL = os.environ.get("DATABASE_URL")

if SECRET_KEY is None:
    raise ValueError("SECRET_KEY is not set in the environment. Please create a .env file.")

# ----------------------------
# Database Setup
# ----------------------------
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# User model
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    todos = relationship("Todo", back_populates="owner", cascade="all, delete-orphan")

# Todo model
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

# ----------------------------
# Password & Hashing
# ----------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

def get_password_hash(password):
    # bcrypt has a maximum password length of 72 bytes.
    # Truncating avoids an error for very long passwords.
    password_bytes = password.encode('utf-8')[:72]
    return pwd_context.hash(password_bytes)

def verify_password(plain_password, hashed_password):
    password_bytes = plain_password.encode('utf-8')[:72]
    return pwd_context.verify(password_bytes, hashed_password)

# ----------------------------
# JWT Helpers
# ----------------------------
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
        if username is None:
            return None
        user = db.query(User).filter(User.username == username).first()
        return user
    except JWTError:
        return None

def get_current_user_optional(request: Request, db: Session = Depends(lambda: next(get_db()))):
    token = request.cookies.get("access_token")
    return _get_user_from_token(db, token)

def get_current_user(request: Request, db: Session = Depends(lambda: next(get_db()))):
    user = get_current_user_optional(request, db)
    if user is None:
        # Instead of raising HTTPException, redirect to login
        return RedirectResponse("/login", status_code=303)
    return user

# ----------------------------
# App Setup
# ----------------------------
app = FastAPI(title="To-Do App", description="A simple task management application", version="1.0.0")
# Add session middleware for flash messages
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper for Flash Messages
def flash(request: Request, message: str, category: str = "info"):
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({"message": message, "category": category})

def get_flashed_messages(request: Request):
    return request.session.pop("_messages") if "_messages" in request.session else []

# Add the flash function to the template context
templates.env.globals['get_flashed_messages'] = get_flashed_messages

# ----------------------------
# Routes
# ----------------------------
@app.get("/", response_class=HTMLResponse)
# NEW: Add a 'filter' query parameter to the index route
def index(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    filter: Literal["all", "pending", "completed"] = "all"
):
    if isinstance(user, RedirectResponse): # If get_current_user returned a redirect
        return user
    
    # NEW: Query based on the filter parameter
    all_todos_query = db.query(Todo).filter(Todo.user_id == user.id)

    if filter == "pending":
        todos_query = all_todos_query.filter(Todo.completed == False)
    elif filter == "completed":
        todos_query = all_todos_query.filter(Todo.completed == True)
    else: # "all"
        todos_query = all_todos_query

    todos = todos_query.order_by(Todo.created_at.desc()).all()
    all_todos = all_todos_query.all()

    # The counts should reflect ALL tasks, not just the filtered ones
    completed_count = sum(1 for todo in all_todos if todo.completed)
    pending_count = len(all_todos) - completed_count
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "todos": todos,
        "user": user,
        "completed_count": completed_count,
        "pending_count": pending_count,
        "total_count": len(all_todos),
        "current_filter": filter # NEW: Pass the current filter to the template
    })

# ... (The rest of your main.py file remains the same)
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
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
    flash(request, "Registration successful! Please login.", "success")
    return RedirectResponse("/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        flash(request, "Invalid username or password", "error")
        return templates.TemplateResponse("login.html", {"request": request}, status_code=401)
    
    access_token = create_access_token({"sub": user.username})
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return response

@app.get("/change-password", response_class=HTMLResponse)
def change_password_page(request: Request, user: User = Depends(get_current_user)):
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("change_password.html", {"request": request, "user": user})

@app.post("/change-password")
def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if isinstance(user, RedirectResponse):
        return user
        
    if not verify_password(old_password, user.hashed_password):
        flash(request, "Current password is incorrect", "error")
        return templates.TemplateResponse("change_password.html", {"request": request, "user": user}, status_code=400)
    
    if len(new_password) < 6:
        flash(request, "New password must be at least 6 characters long", "error")
        return templates.TemplateResponse("change_password.html", {"request": request, "user": user}, status_code=400)
    
    if new_password != confirm_password:
        flash(request, "New passwords do not match", "error")
        return templates.TemplateResponse("change_password.html", {"request": request, "user": user}, status_code=400)
    
    if old_password == new_password:
        flash(request, "New password must be different from current password", "error")
        return templates.TemplateResponse("change_password.html", {"request": request, "user": user}, status_code=400)
    
    db_user = db.query(User).filter(User.id == user.id).first()
    db_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    flash(request, "Password changed successfully!", "success")
    return templates.TemplateResponse("change_password.html", {"request": request, "user": user})

@app.post("/add_todo")
# NEW: Add a redirect back to the current filter view after adding a task
def add_todo(request: Request, title: str = Form(...), description: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if isinstance(user, RedirectResponse):
        return user
    if not title.strip():
        flash(request, "Title cannot be empty", "error")
        return RedirectResponse("/", status_code=303)
    
    todo = Todo(title=title.strip(), description=description.strip(), user_id=user.id)
    db.add(todo)
    db.commit()
    flash(request, "Task added successfully.", "success")
    return RedirectResponse("/?filter=pending", status_code=303)

@app.post("/toggle_todo/{todo_id}")
def toggle_todo(request: Request, todo_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if isinstance(user, RedirectResponse):
        return user
    todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == user.id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    todo.completed = not todo.completed
    db.commit()
    # NEW: Get the current filter from the referrer header to stay on the same page
    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=303)


@app.post("/delete_todo/{todo_id}")
def delete_todo(request: Request, todo_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if isinstance(user, RedirectResponse):
        return user
    todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == user.id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    db.delete(todo)
    db.commit()
    flash(request, "Task deleted.", "success")
    # NEW: Get the current filter from the referrer header to stay on the same page
    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=303)


@app.post("/delete_all_completed")
def delete_all_completed(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if isinstance(user, RedirectResponse):
        return user
    db.query(Todo).filter(Todo.user_id == user.id, Todo.completed == True).delete()
    db.commit()
    flash(request, "All completed tasks have been cleared.", "success")
    return RedirectResponse("/", status_code=303)

@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("access_token")
    return response

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy"}