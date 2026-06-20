import re
from app.core.common_passwords import COMMON_PASSWORDS

def validate_password_strength(password: str) -> None:
    """
    Validates that a password:
    - Has at least 12 characters
    - Contains at least 1 uppercase letter
    - Contains at least 1 lowercase letter
    - Contains at least 1 digit
    - Contains at least 1 special character (non-alphanumeric)
    - Is not in the top-1000 common passwords list
    """
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters long.")
    
    if not any(c.isupper() for c in password):
        raise ValueError("Password must contain at least one uppercase letter.")
        
    if not any(c.islower() for c in password):
        raise ValueError("Password must contain at least one lowercase letter.")
        
    if not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one digit.")
        
    # Check for at least one special character (non-alphanumeric)
    if not any(not c.isalnum() for c in password):
        raise ValueError("Password must contain at least one special character (e.g. !@#$%^&*).")

    if password in COMMON_PASSWORDS:
        raise ValueError("Password is too common. Please choose a more secure password.")
