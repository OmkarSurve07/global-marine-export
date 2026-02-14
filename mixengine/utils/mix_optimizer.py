from scipy.optimize import linprog
import numpy as np

FOOD_TOLERANCES = {
    "cp": 0.5,  # Crude Protein ±0.5%
    "fat": 1.0,  # Crude Fat ±1.0%
    "ash": 1.5,  # Total Ash ±1.5%
    "ffa": 0.5,  # Free Fatty Acids ±0.5%
    "moisture": 0.5,  # Moisture ±0.5%
    "fiber": 1.0,  # Crude Fiber ±1.0%
    "tvbn": 1.0  # TVBN ±1.0 (fishmeal freshness indicator)
}


def optimize_mix(samples, total_bags, fixed_samples=None, **targets):
    """
    Optimization for nutritional accuracy with soft constraints.
    - Always returns a feasible solution by minimizing violations beyond tolerances.
    - If perfect match within tolerances, violations = 0.
    - Pre-checks for target achievability ignored since soft constraints handle it.
    """
    fixed_samples = fixed_samples or {}
    n = len(samples)
    # Map targets to nutrient names (strip 'target_')
    targets = {k.replace("target_", "").lower(): v for k, v in targets.items() if v is not None}
    nutrient_list = list(targets.keys())
    m = len(nutrient_list)
    if m == 0:
        return basic_mix(samples, total_bags, fixed_samples)

    # Extract values
    values_dict = {
        "moisture": [s.moisture for s in samples],
        "cp": [s.cp for s in samples],
        "fat": [s.fat for s in samples],
        "tvbn": [s.tvbn for s in samples],
        "ash": [s.ash for s in samples],
        "ffa": [s.ffa for s in samples],
        "fiber": [s.fiber for s in samples],
    }
    values_dict = {k: v for k, v in values_dict.items() if k in nutrient_list}
    # bag_limits = [s.bags_available for s in samples]
    bag_limits = [max(0, s.remaining_quantity) for s in samples]

    # Objective: minimize sum of all violations (upper + lower for each nutrient)
    c = np.zeros(n)  # No cost for x
    c = np.concatenate((c, np.ones(2 * m)))  # Cost 1 for each viol_upper and viol_lower

    # Bounds: x_i in [0, bag_limit_i], violations >= 0
    bounds = [(0, bl) for bl in bag_limits] + [(0, None)] * (2 * m)

    # Equality constraints: total bags + fixed (grouped)
    A_eq = np.zeros((1, n + 2 * m))
    A_eq[0, :n] = 1
    b_eq = [total_bags]

    for key, val in fixed_samples.items():
        # Determine matching samples based on key
        if key.upper() == "F/M":
            matching_indices = [i for i, s in enumerate(samples) if "FISH MEAL" in s.name.upper()]
        elif key.upper() == "HYPRO":
            matching_indices = [i for i, s in enumerate(samples) if "HYPRO" in s.name.upper()]
        else:
            matching_indices = [i for i, s in enumerate(samples) if key.upper() in s.name.upper()]

        if matching_indices:
            # Use current remaining quantity (clamped to >=0) instead of original bags_available
            sum_remaining = sum(bag_limits[i] for i in matching_indices)  # bag_limits already uses remaining_quantity

            # Cap the fixed requirement at what's actually available now
            fixed_bags = min(val, sum_remaining)

            # Create equality constraint row: sum of x_i for matching samples == fixed_bags
            fixed_row = np.zeros(n + 2 * m)
            for i in matching_indices:
                fixed_row[i] = 1
            A_eq = np.vstack((A_eq, fixed_row))
            b_eq.append(fixed_bags)

    A_eq = np.array(A_eq)
    b_eq = np.array(b_eq)

    # Upper and lower soft constraints for each nutrient
    A_ub = []
    b_ub = []
    for j, nutrient in enumerate(nutrient_list):
        tol = FOOD_TOLERANCES.get(nutrient, 0.5)
        t = targets[nutrient]
        v = values_dict[nutrient]

        # Upper: sum(v_i * x_i) - viol_upper_j <= (t + tol) * total_bags
        upper_row = np.zeros(n + 2 * m)
        upper_row[:n] = v
        upper_row[n + j] = -1
        A_ub.append(upper_row)
        b_ub.append((t + tol) * total_bags)

        # Lower: -sum(v_i * x_i) - viol_lower_j <= -(t - tol) * total_bags
        lower_row = np.zeros(n + 2 * m)
        lower_row[:n] = -np.array(v)
        lower_row[n + m + j] = -1
        A_ub.append(lower_row)
        b_ub.append(-(t - tol) * total_bags)

    A_ub = np.array(A_ub) if A_ub else None
    b_ub = np.array(b_ub) if b_ub else None

    result = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method='highs')

    def avg(values, bags_used):
        total_used = sum(bags_used)
        if total_used == 0:
            return 0
        return sum(values[i] * bags_used[i] for i in range(n)) / total_used

    if result.success:
        bags_used = result.x[:n]
        violations = result.x[n:]
        total_violation = sum(violations)

        final_values = {
            nut: avg(values_dict[nut], bags_used) for nut in nutrient_list
        }

        return {
            "success": total_violation == 0,
            "bags_used": [round(b, 2) for b in bags_used],
            "final_values": {k: round(v, 2) for k, v in final_values.items()},
            "total_violation": round(total_violation, 2)  # Sum of excess deviations (total units)
        }
    else:
        return {
            "success": False,
            "reason": "Even with soft constraints, no solution. Check total_bags vs available or fixed values.",
            "details": result.message
        }


def basic_mix(samples, total_bags, fixed_samples):
    n = len(samples)
    c = np.zeros(n)
    A_eq = np.ones((1, n))
    b_eq = [total_bags]

    bag_limits = [max(0, s.remaining_quantity) for s in samples]
    bounds = [(0, bl) for bl in bag_limits]
    for key, val in fixed_samples.items():
        if key.upper() == "F/M":
            matching = [i for i, s in enumerate(samples) if "FISH MEAL" in s.name.upper()]
        elif key.upper() == "HYPRO":
            matching = [i for i, s in enumerate(samples) if "HYPRO" in s.name.upper()]
        else:
            matching = [i for i, s in enumerate(samples) if key.upper() in s.name.upper()]

        if matching:
            sum_remaining = sum(bag_limits[i] for i in matching)
            fixed_bags = min(val, sum_remaining)

            fixed_row = np.zeros(n)
            for i in matching:
                fixed_row[i] = 1
            A_eq = np.vstack((A_eq, fixed_row))
            b_eq.append(fixed_bags)

    result = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method='highs')
    if result.success:
        return {"success": True, "bags_used": [round(b, 2) for b in result.x], "final_values": {}, "total_violation": 0}
    else:
        return {"success": False, "reason": result.message}


def get_achievable_range(samples, nutrient, total_bags):
    n = len(samples)
    values = np.array([getattr(s, nutrient) or 0 for s in samples])
    bag_limits = [max(0, s.remaining_quantity) for s in samples]

    A_eq = np.ones((1, n))
    b_eq = np.array([total_bags])
    bounds = [(0, bl) for bl in bag_limits]

    # Maximize nutrient
    c_max = -values
    res_max = linprog(c_max, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")

    # Minimize nutrient
    c_min = values
    res_min = linprog(c_min, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")

    if not res_max.success or not res_min.success:
        return None

    max_val = -res_max.fun / total_bags
    min_val = res_min.fun / total_bags

    return round(max(0, min_val), 2), round(max(0, max_val), 2)


def get_closest_feasible_targets(samples, total_bags, targets_dict, fixed_samples=None):
    n = len(samples)
    nutrients = list(targets_dict.keys())
    m = len(nutrients)

    bag_limits = [max(0, s.remaining_quantity) for s in samples]

    # Extract nutrient values matrix
    values_matrix = np.array([
        [getattr(s, nut.lower()) or 0 for s in samples]
        for nut in nutrients
    ])

    # Variables:
    # x_i (n samples)
    # deviation_j_pos
    # deviation_j_neg
    total_vars = n + 2 * m

    c = np.zeros(total_vars)
    c[n:] = 1  # minimize total deviation

    bounds = [(0, bl) for bl in bag_limits] + [(0, None)] * (2 * m)

    # Equality: sum(x) = total_bags
    A_eq = np.zeros((1, total_vars))
    A_eq[0, :n] = 1
    b_eq = np.array([total_bags])

    fixed_samples = fixed_samples or {}

    for key, val in fixed_samples.items():
        if key.upper() == "F/M":
            matching_indices = [i for i, s in enumerate(samples) if "FISH MEAL" in s.name.upper()]
        elif key.upper() == "HYPRO":
            matching_indices = [i for i, s in enumerate(samples) if "HYPRO" in s.name.upper()]
        else:
            matching_indices = [i for i, s in enumerate(samples) if key.upper() in s.name.upper()]

        if matching_indices:
            row = np.zeros(total_vars)
            for i in matching_indices:
                row[i] = 1
            A_eq = np.vstack((A_eq, row))
            b_eq = np.append(b_eq, val)

    A_ub = []
    b_ub = []

    for j, nutrient in enumerate(nutrients):
        target = targets_dict[nutrient]

        row_upper = np.zeros(total_vars)
        row_upper[:n] = values_matrix[j]
        row_upper[n + j] = -1
        A_ub.append(row_upper)
        b_ub.append(target * total_bags)

        row_lower = np.zeros(total_vars)
        row_lower[:n] = -values_matrix[j]
        row_lower[n + m + j] = -1
        A_ub.append(row_lower)
        b_ub.append(-target * total_bags)

    res = linprog(c,
                  A_ub=np.array(A_ub),
                  b_ub=np.array(b_ub),
                  A_eq=A_eq,
                  b_eq=b_eq,
                  bounds=bounds,
                  method="highs")

    if not res.success:
        return None

    x = res.x[:n]

    # Calculate final achievable nutrient values
    recommended = {}
    for j, nutrient in enumerate(nutrients):
        total = sum(values_matrix[j][i] * x[i] for i in range(n))
        recommended[nutrient] = round(total / total_bags, 2)

    return recommended
