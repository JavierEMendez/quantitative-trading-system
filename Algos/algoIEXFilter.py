from pylivetrader.api import *
from pylivetrader.algorithm import date_rules, time_rules
from zipline.pipeline import Pipeline
from pipeline_live.data.polygon.filters import (
        IsPrimaryShareEmulation as IsPrimaryShare)
from pylivetrader.finance.execution import LimitOrder
from pipeline_live.data.iex.fundamentals import IEXCompany, IEXKeyStats
from pipeline_live.data.iex.factors import (
    SimpleMovingAverage, AverageDollarVolume)
from pipeline_live.data.iex.pricing import USEquityPricing
def initialize(context):
    # Schedule our rebalance function to run at the end of
    # each day, when the market closes
    #set_slippage(slippage.FixedSlippage(spread=0.0, volume_limit=1))
    #set_slippage(slippage.FixedBasisPointsSlippage(basis_points=0, volume_limit=100))
    #set_slippage(slippage.VolumeShareSlippage(0))
    schedule_function(
        my_rebalance,
        date_rules.every_day(),
        time_rules.market_close(minutes=1  )
    )

    # Create our pipeline and attach it to our algorithm.
    my_pipe = make_pipeline()
    attach_pipeline(my_pipe, 'my_pipeline')



def make_pipeline():
    # Filter for primary share equities. IsPrimaryShare is a built-in filter.
    primary_share = IsPrimaryShare()

    # Not when-issued equities.
    not_wi = ~IEXCompany.symbol.latest.endswith('.WI')

    # Equities without LP in their name, .matches does a match using a regular
    # expression
    not_lp_name = ~IEXCompany.companyName.latest.matches('.* L[. ]?P.?$')

    # Equities whose most recent Morningstar market cap is not null have
    # fundamental data and therefore are not ETFs.
    have_market_cap = IEXKeyStats.marketcap.latest >= 1
       
    tradeable_stocks = (
        primary_share
        & not_wi
        & not_lp_name
        & have_market_cap)
    longs = USEquityPricing.close.latest.top(50,mask=tradeable_stocks)
    shorts = SimpleMovingAverage(inputs=[USEquityPricing.close], window_length=10, mask=tradeable_stocks).percentile_between(20,22)    

    return Pipeline(
        columns={
            'longs':  longs,
            'shorts': shorts,
        },
        screen=tradeable_stocks& (shorts | longs)
    
    )

def compute_target_weights(context, data):
    """
    Compute ordering weights.
    """

    # Initialize empty target weights dictionary.
    # This will map securities to their target weight.
    weights = {}

    # If there are securities in our longs and shorts lists,
    # compute even target weights for each security.
    if context.longs :
        long_weight = 0.5 / len(context.longs)
    if context.shorts:
        short_weight = -0.5 / len(context.shorts)
    #if ~(context.longs & context.shorts):
    #    return weights

    # Exit positions in our portfolio if they are not
    # in our longs or shorts lists.
    for security in context.portfolio.positions:
        if security not in context.longs and security not in context.shorts and data.can_trade(security):
            weights[security] = 0

    for security in context.longs:
        weights[security] = long_weight

    for security in context.shorts:
        weights[security] = short_weight

    return weights

def before_trading_start(context, data):
    """
    Get pipeline results.
    """

    # Gets our pipeline output every day.
    pipe_results = pipeline_output('my_pipeline')

    # Go long in securities for which the 'longs' value is True,
    # and check if they can be traded.
    context.longs = []
    for sec in pipe_results[pipe_results['longs']].index.tolist():
        if data.can_trade(sec):
            context.longs.append(sec)
            #print(context.longs)
    #print('Longs: ')       
    #print(context.longs)
    # Go short in securities for which the 'shorts' value is True,
    # and check if they can be traded.
    context.shorts = []
    for sec in pipe_results[pipe_results['shorts']].index.tolist():
        if data.can_trade(sec):
            context.shorts.append(sec)
    #print('Shorts: ')
    #print(context.shorts)
    
   
    
def my_rebalance(context, data):
    """
    Rebalance daily
    """
    for security in context.portfolio.positions:
        #print('selling everything')
        #print(stock)
        order_target_percent(security, 0.0)  
    # Calculate target weights to rebalance
    #print(context)
    target_weights = compute_target_weights(context, data)
    #print(target_weights)

    # If we have target weights, rebalance our portfolio
    n = len(context.longs)
    for security in range(0, n):
        if target_weights:
            order_target_percent(context.longs[security], 0.5 / len(context.longs))
    n = len(context.shorts)
    for security in range(0, n):
        if target_weights:
            order_target_percent(context.shorts[security], -0.5 / len(context.shorts))