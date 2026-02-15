from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt, JWTError
from pydantic import BaseModel

# Imports from your other files
from database import engine, get_db
import models 

# --- SCHEMAS ---
class UserSchema(BaseModel):
    username: str
    password: str
    is_admin: bool = False

# Create the tables in the database
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- SECURITY ---
SECRET_KEY = "my-secret-key" 
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_token(username: str):
    expire = datetime.utcnow() + timedelta(minutes=30)
    details = {"username": username, "exp": expire}
    return jwt.encode(details, SECRET_KEY, algorithm=ALGORITHM)

# --- DEPENDENCIES ---
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("username")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
        
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def check_admin_role(user: models.User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only!")
    return user

# --- ROUTES ---

@app.post("/signup")
def signup(user: UserSchema, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="User already exists")
    
    hashed_pw = get_password_hash(user.password)
    new_user = models.User(username=user.username, password_hash=hashed_pw, is_admin=user.is_admin)
    db.add(new_user)
    db.commit()
    return {"message": "User created"}

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect login")
    
    token = create_token(user.username)
    return {"access_token": token, "token_type": "bearer"}

@app.post("/items")
def add_item(name: str, quantity: int, db: Session = Depends(get_db), admin: models.User = Depends(check_admin_role)):
    # Protected Route: Only Admins can add items
    new_item = models.Item(name=name, quantity=quantity)
    db.add(new_item)
    db.commit()
    return {"message": "Item added"}

@app.get("/items")
def view_inventory(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # Protected Route: Any logged in user can view
    return db.query(models.Item).all()