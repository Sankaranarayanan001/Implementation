import pandas as pd

data = pd.read_csv('train.csv')

# Correlation with target (signed — shows direction too)
correlations = data.corr()['price_range'].sort_values(ascending=False)
print("Correlation with price_range (signed):")
print(correlations)

# Correlation with target (absolute — shows strength only)
correlations_abs = data.corr()['price_range'].drop('price_range').abs().sort_values(ascending=False)
print("\nCorrelation with price_range (by strength):")
print(correlations_abs)

# Top 10 features
top_10 = correlations_abs.head(10).index.tolist()
print("\nTop 10 correlated features:")
print(top_10)