
def classify_density(count, halting, speed):
    if count == 0:
        return "EMPTY"
    elif halting >= 3 or speed < 2:
        return "HIGH"
    elif halting >= 1 or count >= 5 or speed < 5:
        return "MEDIUM"
    return "LOW"


def get_lane_density_report(traci):
    report = {}

    for lane_id in traci.lane.getIDList():
        if lane_id.startswith(":"):
            continue

        count = traci.lane.getLastStepVehicleNumber(lane_id)
        halting = traci.lane.getLastStepHaltingNumber(lane_id)
        speed = traci.lane.getLastStepMeanSpeed(lane_id)

        report[lane_id] = {
            "vehicles": count,
            "halting": halting,
            "mean_speed_mps": round(speed, 2),
            "density": classify_density(count, halting, speed)
        }

    return report
