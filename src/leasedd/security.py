import hashlib,hmac,secrets

def password_hash(password):
    salt=secrets.token_hex(16)
    hashed=hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
    return f'{salt}:{hashed}'

def verify_password(password,stored):
    salt,expected=stored.split(':')
    actual=hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
    return hmac.compare_digest(actual,expected)

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()
