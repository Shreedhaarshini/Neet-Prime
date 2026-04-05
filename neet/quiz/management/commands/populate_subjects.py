from django.core.management.base import BaseCommand
from quiz.models import Subject

class Command(BaseCommand):
    help = 'Populates the Subject table with default subjects.'

    def handle(self, *args, **kwargs):
        subjects = ['Physics', 'Chemistry', 'Maths']
        for subject_name in subjects:
            subject, created = Subject.objects.get_or_create(name=subject_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created subject "{subject_name}"'))
            else:
                self.stdout.write(self.style.WARNING(f'Subject "{subject_name}" already exists'))

        self.stdout.write(self.style.SUCCESS('Subject population complete!'))
