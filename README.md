# **User-Specific To-Do App with FastAPI & JWT Authentication**

A **secure, user-specific To-Do application** built with **FastAPI** and **SQLite**, featuring **JWT authentication** and a **simple web UI**. Each user can register, log in, and manage their personal tasks — creating, reading, updating, and deleting only their own todos.

---

### **Features**

* **User Authentication**: Register and log in with JWT-secured tokens.
* **User-Specific Tasks**: Each user sees only their own todos.
* **CRUD Operations**: Full Create, Read, Update, Delete functionality.
* **Background Logging**: Logs todo operations in a file.
* **Interactive Web UI**: Simple front-end to manage todos easily.
* **SQLite Database**: Lightweight, file-based storage for local development.
* **REST API**: Fully RESTful endpoints for integration with other apps.

---

### **Tech Stack**

* **Backend**: FastAPI, Python
* **Database**: SQLite (can be replaced with PostgreSQL for production)
* **Authentication**: JWT (JSON Web Tokens)
* **Frontend**: HTML, CSS, JavaScript
* **Password Security**: bcrypt hashing via passlib

---

### **Getting Started**

1. **Clone the repo**:

```bash
git clone https://github.com/Nandhana-AM/To-Do-App.git
cd To-Do-App
```

2. **Create a virtual environment**:

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. **Install dependencies**:

```bash
pip install -r requirements.txt
```

4. **Run the app**:

```bash
uvicorn main:app --reload
```

5. **Open in browser**:

* Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* Web UI: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

### **Future Enhancements**

* Switch to **PostgreSQL** for production-ready deployment.
* Add **public/shared todo lists** for collaboration.
* Improve UI with **React or Vue** for a more dynamic experience.
* Deploy on **cloud platforms** such as Render, Railway, or Heroku.
