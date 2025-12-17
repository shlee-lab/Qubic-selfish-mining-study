import numpy as np

def calculate_implied_delay():
    print("Calculating Implied Propagation Delay...")
    
    # Parameters
    alpha = 0.258  # Qubic's Hashrate Share
    win_rate_obs = 0.352  # Observed Win Rate in True Races
    block_time_seconds = 120  # Monero Block Time
    
    # Qubic's lambda (blocks per second)
    # Total network finds 1 block per 120s
    # Qubic finds alpha blocks per 120s
    lambda_q = alpha / block_time_seconds
    
    print(f"Parameters:")
    print(f"  Alpha (Expected Win Rate): {alpha:.4f}")
    print(f"  Observed Win Rate: {win_rate_obs:.4f}")
    print(f"  Monero Block Time: {block_time_seconds}s")
    print(f"  Qubic Hashrate (lambda_q): {lambda_q:.6f} blocks/s")
    
    # Formula derived from:
    # P(Win) = P(Q finds in dt) + P(Q doesn't find in dt) * alpha
    # P(Win) = (1 - exp(-lambda_q * dt)) + exp(-lambda_q * dt) * alpha
    #
    # Solving for dt:
    # P(Win) - 1 = exp(-lambda_q * dt) * (alpha - 1)
    # (P(Win) - 1) / (alpha - 1) = exp(-lambda_q * dt)
    # ln( (1 - P(Win)) / (1 - alpha) ) = -lambda_q * dt
    # dt = - (1 / lambda_q) * ln( (1 - P(Win)) / (1 - alpha) )
    
    numerator = 1 - win_rate_obs
    denominator = 1 - alpha
    ratio = numerator / denominator
    
    dt = -(1 / lambda_q) * np.log(ratio)
    
    print(f"\nResults:")
    print(f"  Implied Time Advantage (Delta t): {dt:.4f} seconds")
    
    # Check sensitivity
    print(f"\nSensitivity Analysis:")
    for wr in [0.30, 0.35, 0.40]:
        r = (1 - wr) / (1 - alpha)
        t = -(1 / lambda_q) * np.log(r)
        print(f"  If Win Rate was {wr:.2f}, Delta t would be {t:.2f}s")

if __name__ == "__main__":
    calculate_implied_delay()
