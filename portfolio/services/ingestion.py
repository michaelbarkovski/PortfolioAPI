from decimal import Decimal 
import requests
from django.conf import settings 
from portfolio.models import Asset, Price

def fetch_daily_prices(identifier: str) -> dict:
    
    #Calls aAlpha Vantage daily time series endpoint for a given symbol and returns a price and date time. 

    #read API key from settings
    api_key = settings.ALPHAVANTAGE_API_KEY
    if not api_key:
        raise ValueError("Missing API Key environment variable.")

    url = "https://www.alphavantage.co/query" #base alpha vantage endpoint 

    #query parameters required by alpha vatnage API
    params = {
        "function": "TIME_SERIES_DAILY", #daily prices 
        "symbol": identifier, #stock symbol like AAPL for Apple for example 
        "outputsize": "compact", #compact gives the most recent 100 data points \
        "apikey": api_key
    }

    #make HTTP request
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status() 
    data = response.json()

    if "Error Message" in data:
        raise ValueError(f"Alpha Vantage error: {data['Error Message']}") #this means alpha vantage sends errors in JSON rather than HTTP status codes 

    if "Note" in data:
        raise ValueError(f"Alpha Vantage throttled: {data['Note']}") #if rate limit exceeded, alpha vantage returns a note field, this error detects this instead of interpretting this as data

    series = data.get("Time Series (Daily)") #extract the main series dictionary 
    if not series:
        raise ValueError("Unexpected Alpha Vantage response format. Missing Series (Daily)")
    
    return series

def ingest_asset_prices(identifier: str) -> dict:
    '''
    Upserts (if a asset, date, row exists, update it, if not, create it) daily closing prices for the given asset identifer into the databse 
    returns summary dict with created and updated counts 
    '''
    asset, created = Asset.objects.get_or_create(
    identifier=identifier,
    defaults={"name": identifier}
    )
    series = fetch_daily_prices(identifier) #fetch raw daily series data from ALpha Vantage
    created = 0
    updated = 0
 
    for date_str, ohlc in series.items(): #date_str: date, #ohlc: price fields
        close_str = ohlc.get("4. close") #clossing price
        if close_str is None:
            continue #skip if repose format is missing close field 
        
        obj, was_created = Price.objects.update_or_create(
            asset=asset,
            date=date_str, 
            defaults = {
                "closing_price": Decimal(close_str), #store closing price as decimal 
                "data_source": "alpha_vantage", #record provenance 
            },
        )
        if was_created:
            created +=1
        else:
            updated +=1
    
    return {
        "asset": identifier, 
        "created": created,
        "updated": updated,
    }

    

