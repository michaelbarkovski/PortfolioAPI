from django.core.management.base import BaseCommand
from portfolio.services.ingestion import ingest_asset_prices


class Command(BaseCommand):
    help = "Ingest daily prices for an asset identifier from Alpha Vantage."

    def add_arguments(self, parser):
        parser.add_argument("identifier", type=str) #positional argument: identifier eg AAPL

    def handle(self, *args, **options):
        identifier = options["identifier"] #read identifier provided on CLI      
        result = ingest_asset_prices(identifier) #call ingestion service
        self.stdout.write(self.style.SUCCESS(str(result))) #print success message to console