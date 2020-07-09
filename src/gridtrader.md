# Developer Notes

## trade_id is actually orderNumber

When you successfully place a trade on Polo, you get an orderNumber. In my code, this is referred to as a 
trade_id in the Grid class. This is tragic, because the fills of an order have both a globalTradeID and a
tradeID, but unfortunately, these are not orderNumbers. To summarize: trade_id is what the Polo API refers
to as orderNumber and when you see things like f['tradeID'] it truly is referring to an order number and
in no way the same thing as the trade_id you see in my grid!

## Reciprocal bookkeeping

Reciprocals are a dictionary of form self.reciprocal[market][buysell][reciprocantTradeId] with the dictionary
value being an instance and subclass of ReciprocalTrade. "self" is an instance of class GridTrader. 