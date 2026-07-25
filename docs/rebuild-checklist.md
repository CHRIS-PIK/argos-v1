# Clean rebuild checklist

1. Merge the migration correction pull request.
2. Update the local `main` branch.
3. Confirm the definitive credentials are present only in the local `.env` file.
4. Stop the stack and remove containers, volumes, and orphan resources.
5. Start the stack again so the database is created from scratch and all migrations run in order.
6. Validate container health and inspect migration logs before enabling the collectors.
