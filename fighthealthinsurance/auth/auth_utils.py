# Different clinics will have different "domains" and the django username will be the user visible username + a clinic name seperated by a panda unicode

def validate_username(username: str) -> bool:
    return "🐼" not in username


def combine_domain_and_username(username: str, domain: str) -> str:
    # TODO: Resolve domain str to ID since folks might have the domain change.
    return f"{username}🐼{domain}"
