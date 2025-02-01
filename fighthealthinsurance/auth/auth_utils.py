def validate_username(username: str) -> bool:
    return "🐼" not in username

def combine_domain_and_username(username: str, domain: str) -> str:
    return f"{username}🐼{domain}"
