import logging
from typing import List, Optional, Dict, Any
from api.types.api_models.agent import FilterRules

logger = logging.getLogger(__name__)

def get_domain(email: str) -> Optional[str]:
    """Extracts the domain from an email address."""
    if '@' in email:
        return email.split('@')[-1]
    return None

def passes_filter(email_from: str, rules: Dict[str, Any]) -> bool:
    """
    Checks if an email passes the filter rules.
    - Blacklists have priority.
    - If a whitelist is defined, the email must be on it.
    """
    if not email_from or not rules:
        return True

    from_domain = get_domain(email_from)
    logger.info(f"From domain: {from_domain}")

    # Use .get() to safely access dictionary keys
    email_blacklist = rules.get("email_blacklist", [])
    domain_blacklist = rules.get("domain_blacklist", [])
    email_whitelist = rules.get("email_whitelist", [])
    domain_whitelist = rules.get("domain_whitelist", [])

    logger.info(f"Email blacklist: {email_blacklist}")
    logger.info(f"Domain blacklist: {domain_blacklist}")
    logger.info(f"Email whitelist: {email_whitelist}")
    logger.info(f"Domain whitelist: {domain_whitelist}")

    # 1. Blacklist checks
    if email_blacklist and email_from in email_blacklist:
        logger.info(f"Email from '{email_from}' is on the email blacklist. Filtering out.")
        return False
    if from_domain and domain_blacklist and from_domain in domain_blacklist:
        logger.info(f"Domain '{from_domain}' is on the domain blacklist. Filtering out.")
        return False

    # 2. Whitelist checks (only if the whitelist is not empty)
    # If whitelists are defined, the email *must* match one of them.
    passes_email_whitelist = True
    if email_whitelist:
        passes_email_whitelist = email_from in email_whitelist
    
    passes_domain_whitelist = True
    if domain_whitelist and from_domain:
        passes_domain_whitelist = from_domain in domain_whitelist
    elif domain_whitelist and not from_domain: # has whitelist but no domain on email
        passes_domain_whitelist = False

    # If either whitelist is active and not passed, filter out the email.
    # This logic means: if you use a whitelist, it must be satisfied.
    if email_whitelist and not passes_email_whitelist:
        logger.info(f"Email from '{email_from}' is not on the email whitelist. Filtering out.")
        return False

    if domain_whitelist and not passes_domain_whitelist:
        logger.info(f"Domain '{from_domain}' is not on the domain whitelist. Filtering out.")
        return False

    logger.info("Email passes all filter rules.")
    return True 