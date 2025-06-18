import time
from imap_tools import MailBox
from shared.app_settings import load_app_settings

def main():
    """
    Polls an IMAP inbox and creates a draft for each new email.
    It will wait until settings are configured in Redis before starting.
    """
    print("Trigger service started.")
    last_uid = None

    while True:
        try:
            # Clear the cache to fetch the latest settings on each cycle
            load_app_settings.cache_clear()
            app_settings = load_app_settings()

            # Check if all required settings for this service are present
            if app_settings.IMAP_SERVER and app_settings.IMAP_USERNAME and app_settings.IMAP_PASSWORD:
                print(f"Settings loaded for {app_settings.IMAP_USERNAME}. Checking for mail...")

                with MailBox(app_settings.IMAP_SERVER).login(app_settings.IMAP_USERNAME, app_settings.IMAP_PASSWORD, initial_folder='INBOX') as mailbox:
                    
                    # If last_uid is not set, this is the first successful run.
                    # Fetch existing UIDs to avoid processing all emails in the inbox.
                    if last_uid is None:
                        uids = mailbox.uids()
                        if uids:
                            last_uid = uids[-1]
                            print(f"Monitoring for new emails with UID greater than {last_uid}.")
                        else:
                            print("No existing emails found. Monitoring for all new emails.")

                    query = "ALL"
                    if last_uid:
                        query = f'UID {int(last_uid) + 1}:*'
                    
                    for msg in mailbox.fetch(query):
                        print("--------------------")
                        print(f"New Email Received:")
                        print(f"  UID: {msg.uid}")
                        print(f"  From: {msg.from_}")
                        print(f"  To: {msg.to}")
                        print(f"  Date: {msg.date_str}")
                        print(f"  Subject: {msg.subject}")
                        body = msg.text or msg.html
                        print(f"  Body: {body[:100].strip()}...")
                        print("--------------------")
                        
                        last_uid = msg.uid
            else:
                print("IMAP settings are not fully configured in Redis. Skipping poll cycle. Will check again in 60 seconds.")

        except Exception as e:
            print(f"An unexpected error occurred: {e}. Skipping poll cycle.")

        # Poll every 60 seconds
        time.sleep(60)

if __name__ == "__main__":
    main() 