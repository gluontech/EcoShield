from src.core.models.results import ReturnPeriodLoss, compute_eal_trapezoidal

def run():
    points = [
        ReturnPeriodLoss(return_period_years=10, exceedance_probability=0.1, damage_ratio=0.1, loss_usd=10000),
        ReturnPeriodLoss(return_period_years=50, exceedance_probability=0.02, damage_ratio=0.5, loss_usd=50000),
        ReturnPeriodLoss(return_period_years=100, exceedance_probability=0.01, damage_ratio=0.8, loss_usd=80000),
    ]
    eal = compute_eal_trapezoidal(points)
    print(f"EAL: {eal}")

if __name__ == "__main__":
    run()
