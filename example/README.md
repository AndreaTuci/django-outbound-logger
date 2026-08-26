# Example project

A small Django project to try the library by hand.

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Then open http://127.0.0.1:8000/ and follow the five links: a message that goes
out, one refused by a flaky server, a call that answers, one to a dead endpoint,
and one answered 503 and then 200 to the retry. Whatever failed can be sent
again from the admin, with the action *Send the selected messages again*, or
from the shell:

```bash
.venv/bin/python manage.py retry_failed_emails --dry-run
.venv/bin/python manage.py retry_failed_emails
.venv/bin/python manage.py retry_failed_requests --include-server-errors
```

The delivered messages are printed to the terminal running the server. The
database is `example/db.sqlite3`: delete it to start over.
