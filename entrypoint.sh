#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Run the database initialization script
echo "--- Starting entrypoint script ---"
python3 scripts/init_db.py

# The 'exec "$@"' command runs the command passed to the script.
# In our Dockerfile, this will be the CMD ["/usr/bin/supervisord", ...].
# Using 'exec' is important because it replaces the shell process with
# the new process, allowing it to receive signals correctly.
echo "--- Handing over to the main container command (CMD) ---"
exec "$@" 