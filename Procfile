release: python manage.py migrate --noinput && python manage.py init_saas && python manage.py crear_superusuario
web: gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 3 --timeout 60
