"""Explicit interactive owner provisioning; no passwords in arguments or defaults."""
from getpass import getpass
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Create the owner using an interactive password prompt; never modifies an existing account.'
    def add_arguments(self, parser):
        parser.add_argument('--username', default='owenosa')
        parser.add_argument('--email', default='owen.osagiede@gmail.com')
    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.filter(username=options['username']).exists():
            raise CommandError('Owner already exists; use the documented password recovery command.')
        user = User(username=options['username'], email=options['email'], is_staff=True, is_superuser=True)
        password = getpass('Owner password: ')
        if password != getpass('Confirm owner password: '):
            raise CommandError('Passwords do not match')
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        user.set_password(password)
        user.save()
        self.stdout.write('Owner created. No password was logged.')
