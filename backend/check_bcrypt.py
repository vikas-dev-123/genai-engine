from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto", bcrypt__rounds=12)

try:
    print("Hashing 'password123'...")
    h = pwd_context.hash('password123')
    print('OK:', h)
except Exception as e:
    print('ERROR:', type(e).__name__, e)
