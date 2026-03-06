from decimal import Decimal 
import math 
from collections import defaultdict
from portfolio.models import Holding

TRADING_DAYS_PER_YEAR = 252 #approx trading days per year (exlcuding weekends, holidays etc)

def calculate_portfolio_metrics(portfolio, missing_data_policy="intersection", risk_free_rate=0.02,):
    """
    Core finanical engine 
    steps:
    1. gather holdings 
    2. build alligned return series 
    3. compute portfolio returns
    4. compute metrics 
    """
    '''
    Adaption to handle missing data 
    parameters: 
        portfolio
    '''


    holdings = portfolio.holdings.select_related("asset").all()
    if not holdings.exists(): #error if a portfolio has no asets 
        raise ValueError("Portfolio has no holdings.")

    #1. build date -> return mapping for each asset
    asset_returns = {}
    for holding in holdings:
        prices = list(holding.asset.prices.order_by("date").values_list("date", "closing_price"))
        if len(prices) < 2:
            raise ValueError(f"Not enough price data for {holding.asset.identifier}") #error if there is insufficient price info about a particular asset 
        
        returns_by_date = {}

        for i in range(1, len(prices)):
            date_today = prices[i][0]
            price_today = float(prices[i][1])
            price_yesterday = float(prices[i-1][1])
            r = (price_today / price_yesterday) - 1

            returns_by_date[date_today] = r #return for date_today
        
        asset_returns[holding.asset.id] = returns_by_date
    #2. determine which dates to use 

    all_dates_sets = [
        set(asset_returns[asset_id].keys())
        for asset_id in asset_returns
    ]
    if missing_data_policy == "intersection":
        valid_dates=set.intersection(*all_dates_sets) #only use dates that all assets share 
    elif missing_data_policy == "forward_fill":
        valid_dates = set.union(*all_dates_sets) #use union of all dates 
    else: 
        raise ValueError("Invalid missing_data_policy")
    
    valid_dates = sorted(valid_dates)
    if not valid_dates:
        raise ValueError("No valid return dates available after alignment.")

    #3. Building aligned portfoliio return series

    portfolio_returns = []
    last_known_returns = defaultdict(lambda: 0) #track last known return per asset for forward fill 

    for date in valid_dates:
        rp_t = 0

        for holding in holdings:
            weight = float(holding.weight)
            asset_id = holding.asset.id

            returns_for_asset = asset_returns[asset_id]

            if date in returns_for_asset:
                r = returns_for_asset[date]
                last_known_returns[asset_id] = r
            else:
                if missing_data_policy == "intersection":
                    continue
                elif missing_data_policy == "forward_fill":
                    r = last_known_returns[asset_id]

            rp_t += weight * r

        portfolio_returns.append(rp_t)



    #4. compute metrics 

    mean_daily = sum(portfolio_returns) / len(portfolio_returns)
    annual_return = mean_daily * TRADING_DAYS_PER_YEAR
    variance = sum((r-mean_daily) ** 2 for r in portfolio_returns) / (len(portfolio_returns)-1)
    daily_vol = math.sqrt(variance)
    annual_vol = daily_vol * math.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (annual_return -risk_free_rate) / annual_vol if annual_vol != 0 else 0 

    #5. max drawdown 
    cumulative = 1
    peak = 1
    max_drawdown = 0

    for r in portfolio_returns:
        cumulative *= (1+r)
        peak = max(peak, cumulative)
        drawdown = (cumulative - peak) / peak
        max_drawdown = min(max_drawdown, drawdown)

    return{
        "annualised_return": round(annual_return, 6),
        "annualised_volatility": round (annual_vol, 6),
        "sharpe_ratio": round(sharpe, 6),
        "max_drawdown": round(max_drawdown, 6),
        "missing_data_policy": missing_data_policy,
    }

