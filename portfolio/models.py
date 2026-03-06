from django.db import models
from django.contrib.auth.models import User

#Asset Model: Represents a financial instrument e.g. an apple stock, microsfot stock etc. 
#This table stores general information about each asset. it does not store prices
class Asset(models.Model):
    identifier = models.CharField(max_length=20, unique=True) #short identifier like "MSFT" (microsoft), unqiue True ensures no duplicates
    name = models.CharField(max_length=100, blank=True) #Full name for asset

    def __str__(self):
        return self.identifier


#Price Model:
'''
Stores Historical Price data for each asset 
one asset can have many price entries (onoe to many)
asset -> prices 
each row represents: asset X had a closing price Y on date Z
'''

class Price(models.Model):
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="prices"
    )
    date = models.DateField() #date of given price
    closing_price = models.DecimalField(max_digits=12, decimal_places=4) #closing price for that date

    data_source = models.CharField(max_length=50, default="alpha_vantage") #external stock API for real and updated prices 
    ingested_at = models.DateTimeField(auto_now=True) #when this row was last updated, auto_now updates this timestamp each time the row is saved
    
    class Meta:
        #preventing duplicate price entries (you cannot have two pries for same asset on same date)
        unique_together =("asset", "date")
        ordering = ["date"] #order price by ascending date 

    def __str__(self):
        return f"{self.asset.identifier} {self.date} {self.closing_price}"

#Portfolio Model
'''
Represents an investor's portfolio 
does not store weights directly 
'''
class Portfolio(models.Model):
    name = models.CharField(max_length=100) #portfolio name chosen by user 
    date_created = models.DateTimeField(auto_now_add=True) #automatically records when portfolio was created
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="portfolios") #map user to their own portfolios for authentication so a user can only see their own portfolios

    def __str__(self):
        return self.name

#Holding Model
'''
Connects Portfolio and Asset 
Shows:
which assets are in a portfolio 
what weight does each asset have 

Many to many relationship between portfolio and asset 
'''

class Holding(models.Model):
    #which portfolio this holding belongs to 
    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name="holdings"
    )

    #which asset is in the portfolio 
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE
    )

    #Portfolio weight of this asset (0.25000 = 25%)
    weight = models.DecimalField(max_digits=6, decimal_places=5)

    class Meta:
        #prevents same asset appearing twice in the same portfolio 
        unique_together = ("portfolio", "asset")
    
    def __str__(self):
        return f"{self.portfolio.name} {self.asset.identifier} {self.weight}"




