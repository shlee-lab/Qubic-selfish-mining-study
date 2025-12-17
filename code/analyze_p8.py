import pandas as pd
import numpy as np

def main():
    # Load data
    print("Loading data...")
    revenue_df = pd.read_csv('period_revenue_stats.csv')
    gamma_df = pd.read_csv('qubic_gamma_period_analysis.csv')

    # Merge on period label
    # Gamma CSV has 'period' column (P1, P2...), Revenue CSV has 'label' column (P1, P2...)
    merged = pd.merge(revenue_df, gamma_df, left_on='label', right_on='period')

    # Filter for P8
    p8 = merged[merged['label'] == 'P8'].iloc[0]

    # Extract values
    alpha = p8['alpha_x']  # Revenue CSV alpha (should be same)
    gamma = p8['gamma']
    R_observed = p8['R']
    N = p8['total_blocks']

    # Calculate Expected Revenue (R_selfish)
    a = alpha
    g = gamma
    
    # Formula for R_selfish (Eyal & Sirer)
    num = a*(1-a)**2*(4*a + g*(1-2*a)) - a**3
    den = 1 - a*(1 + (2-a)*a)
    R_expected = num / den

    # Calculate Standard Error
    # Revenue R is a ratio, but we can approximate the variance of the revenue share
    # For a binomial process (simplified), variance is p(1-p)/N
    # Here p = R_expected
    sigma = np.sqrt(R_expected * (1 - R_expected) / N)

    # Calculate Z-score
    z_score = (R_observed - R_expected) / sigma

    print(f'P8 Analysis:')
    print(f'  Alpha: {alpha:.4f}')
    print(f'  Gamma: {gamma:.4f}')
    print(f'  Total Blocks (N): {N}')
    print(f'  Observed Revenue (R): {R_observed:.4f}')
    print(f'  Expected Revenue (R_exp): {R_expected:.4f}')
    print(f'  Expected Honest Revenue (Alpha): {alpha:.4f}')
    print(f'  Difference (Obs - Exp): {R_observed - R_expected:.4f}')
    print(f'  Standard Error (Sigma): {sigma:.4f}')
    print(f'  Z-Score: {z_score:.4f}')

    if abs(z_score) > 2:
        print("\nConclusion: The deviation is STATISTICALLY SIGNIFICANT (Z > 2).")
        print("It is unlikely to be due to random chance alone.")
    else:
        print("\nConclusion: The deviation is NOT statistically significant (Z < 2).")
        print("It could be explained by random variance (luck).")

if __name__ == "__main__":
    main()
