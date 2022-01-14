# load px4 ulog file

from copy import copy
import math
import numpy as np
from scipy import interpolate

d2r = math.pi / 180.0
r2d = 180.0/ math.pi
mps2kt = 1.94384
m2ft = 1.0 / 0.3048

def px4_norm(q):
    return math.sqrt(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3])

def px4_quat2euler(q):
    #print q
    norm = px4_norm(q)
    if norm > 0.000001:
        # normalize quat
        for i in range(4):
            q[i] /= norm
    # create Euler angles vector from the quaternion
    phi = math.atan2(2.0 * (q[0] * q[1] + q[2] * q[3]),
                     1.0 - 2.0 * (q[1] * q[1] + q[2] * q[2]))
    the = math.asin(2.0 * (q[0] * q[2] - q[3] * q[1]))
    psi = math.atan2(2.0 * (q[0] * q[3] + q[1] * q[2]),
                     1.0 - 2.0 * (q[2] * q[2] + q[3] * q[3]))
    return (phi, the, psi)

def get_section(data, name, id):
    print("section:", name, id)
    for d in data:
        if d.name == name and d.multi_id == id:
            for f in d.field_data:
                print(" ", f.field_name)
            return d
    return None

def load(ulog_file):
    from pyulog.core import ULog    # pip install pyulog
    
    result = {}
    result["imu"] = []
    result["gps"] = []
    result["air"] = []
    result["filter"] = []
    #result["pilot"] = []
    result["act"] = []
    result["ap"] = []

    nav = {}

    messages = ["actuator_outputs",
                "airspeed",
                "sensor_accel",
                "sensor_combined",
                "vehicle_air_data",
                "vehicle_attitude",
                "vehicle_attitude_setpoint",
                "vehicle_global_position",
                "vehicle_gps_position",
                "vehicle_magnetometer",
                "wind_estimate"]
    
    ulog = ULog(ulog_file, messages)
    data = ulog.data_list
    temp_interp = None

    d = get_section(data, "sensor_accel", 0)
    if d is not None:
        imu_temps = []
        for i in range(len(d.data["timestamp"])):
            temp = [
                d.data["timestamp"][i],
                d.data["temperature"][i]
            ]
            imu_temps.append(temp)
        imu_temps = np.array(imu_temps)
        temp_interp = interpolate.interp1d(imu_temps[:,0], imu_temps[:,1],
                                           bounds_error=False,
                                           fill_value='extrapolate')

    hx_interp = None
    hy_interp = None
    hz_interp = None
    d = get_section(data, "vehicle_magnetometer", 0)
    if d is not None:
        mags = []
        for i in range(len(d.data["timestamp"])):
            mag = [
                d.data["timestamp"][i],
                d.data["magnetometer_ga[0]"][i],
                d.data["magnetometer_ga[1]"][i],
                d.data["magnetometer_ga[2]"][i]
            ]
            mags.append(mag)
        mags = np.array(mags)
        hx_interp = interpolate.interp1d(mags[:,0], mags[:,1],
                                         bounds_error=False,
                                         fill_value='extrapolate')
        hy_interp = interpolate.interp1d(mags[:,0], mags[:,2],
                                         bounds_error=False,
                                         fill_value='extrapolate')
        hz_interp = interpolate.interp1d(mags[:,0], mags[:,3],
                                         bounds_error=False,
                                         fill_value='extrapolate')

    d = get_section(data, "sensor_combined", 0)
    if d is not None:
        for i in range(len(d.data["timestamp"])):
            t = d.data["timestamp"][i]
            if temp_interp is None:
                temp = 15
            else:
                temp = float(temp_interp(t))
            imu = {
                "time": t / 1e6,
                "p": d.data["gyro_rad[0]"][i],
                "q": d.data["gyro_rad[1]"][i],
                "r": d.data["gyro_rad[2]"][i],
                "ax": d.data["accelerometer_m_s2[0]"][i],
                "ay": d.data["accelerometer_m_s2[1]"][i],
                "az": d.data["accelerometer_m_s2[2]"][i],
                "temp": temp
            }
            if hx_interp is not None:
                imu["hx"] = float(hx_interp(t))
                imu["hy"] = float(hy_interp(t))
                imu["hz"] = float(hz_interp(t))
            else:
                imu["hx"] = d.data["magnetometer_ga[0]"][i]
                imu["hy"] = d.data["magnetometer_ga[1]"][i]
                imu["hz"] = d.data["magnetometer_ga[2]"][i]
                
            result["imu"].append(imu)

    d = get_section(data, "vehicle_gps_position", 0)
    if d is not None:
        for i in range(len(d.data["timestamp"])):
            gps = {
                "time": d.data["timestamp"][i] / 1e6,
                "unix_sec": d.data["time_utc_usec"][i] / 1e6,
                "lat": d.data["lat"][i] / 1e7,
                "lon": d.data["lon"][i] / 1e7,
                "alt": d.data["alt"][i] / 1e3,
                "vn": d.data["vel_n_m_s"][i],
                "ve": d.data["vel_e_m_s"][i],
                "vd": d.data["vel_d_m_s"][i],
                "sats": d.data["satellites_used"][i]
            }
            if gps["sats"] >= 5:
                result["gps"].append(gps)

    d = get_section(data, "airspeed", 0)
    if d is not None:
        airspeed = []
        for i in range(len(d.data["timestamp"])):
            air = [
                d.data["timestamp"][i],
                d.data["indicated_airspeed_m_s"][i] * mps2kt
            ]
            airspeed.append(air)
        airspeed = np.array(airspeed)
        asi_interp = interpolate.interp1d(airspeed[:,0], airspeed[:,1],
                                          bounds_error=False,
                                          fill_value='extrapolate')
    d = get_section(data, "wind_estimate", 0)
    if d is not None:
        wind = []
        for i in range(len(d.data["timestamp"])):
            wn = d.data["windspeed_north"][i]
            we = d.data["windspeed_east"][i]
            wind_deg = 90 - math.atan2(-wn, -we) * r2d
            wind_kt = math.sqrt( we*we + wn*wn ) * mps2kt
            w = [
                d.data["timestamp"][i],
                wind_deg,
                wind_kt
            ]
            wind.append(w)
        wind = np.array(wind)
        wind_deg_interp = interpolate.interp1d(wind[:,0], wind[:,1],
                                               bounds_error=False,
                                               fill_value='extrapolate')
        wind_kt_interp = interpolate.interp1d(wind[:,0], wind[:,2],
                                              bounds_error=False,
                                              fill_value='extrapolate')

    d = get_section(data, "vehicle_air_data", 0)
    if d is not None:
        for i in range(len(d.data["timestamp"])):
            t = d.data["timestamp"][i]
            air = {
                "time": t / 1e6,
                "static_press": d.data["baro_pressure_pa"][i],
                "diff_press": 0.0, 
                "temp": d.data["baro_temp_celcius"][i],
                "airspeed": float(asi_interp(t)),
                "alt_press": d.data["baro_alt_meter"][i],
                "alt_true": 0,
                "tecs_error_total": 0,
                "tecs_error_diff": 0,
                "wind_dir": float(wind_deg_interp(t)),
                "wind_speed": float(wind_kt_interp(t)),
                "pitot_scale": 1
            }
            result["air"].append(air)
    else:
        d = get_section(data, "airspeed", 0)
        if d is not None:
            airspeed = []
            for i in range(len(d.data["timestamp"])):
                t = d.data["timestamp"][i]
                air = {
                    "time": t / 1e6,
                    "airspeed": d.data["indicated_airspeed_m_s"][i] * mps2kt,
                    "wind_dir": float(wind_deg_interp(t)),
                    "wind_speed": float(wind_kt_interp(t)),
                    "pitot_scale": 1
                }
                result["air"].append(air)

    d = get_section(data, "vehicle_global_position", 0)
    if d is not None:
        poses = []
        for i in range(len(d.data["timestamp"])):
            if "vel_n" in d.data:
                vn = d.data["vel_n"][i]
                ve = d.data["vel_e"][i]
                vd = d.data["vel_d"][i]
            else:
                vn = 0
                ve = 0
                vd = 0
            pos = [
                d.data["timestamp"][i],
                d.data["lat"][i],
                d.data["lon"][i],
                d.data["alt"][i],
                vn,
                ve,
                vd
            ]
            poses.append(pos)
        poses = np.array(poses)
        lat_interp = interpolate.interp1d(poses[:,0], poses[:,1],
                                          bounds_error=False,
                                          fill_value='extrapolate')
        lon_interp = interpolate.interp1d(poses[:,0], poses[:,2],
                                          bounds_error=False,
                                          fill_value='extrapolate')
        alt_interp = interpolate.interp1d(poses[:,0], poses[:,3],
                                          bounds_error=False,
                                          fill_value='extrapolate')
        vn_interp = interpolate.interp1d(poses[:,0], poses[:,4],
                                         bounds_error=False,
                                         fill_value='extrapolate')
        ve_interp = interpolate.interp1d(poses[:,0], poses[:,5],
                                         bounds_error=False,
                                         fill_value='extrapolate')
        vd_interp = interpolate.interp1d(poses[:,0], poses[:,6],
                                         bounds_error=False,
                                         fill_value='extrapolate')

    d = get_section(data, "vehicle_attitude", 0)
    if d is not None:
        for i in range(len(d.data["timestamp"])):
            q = [ d.data["q[0]"][i],
                  d.data["q[1]"][i],
                  d.data["q[2]"][i],
                  d.data["q[3]"][i] ]
            (phi, the, psi) = px4_quat2euler(q)
            t = d.data["timestamp"][i]
            nav = {
                "time": t / 1e6,
                "lat": float(lat_interp(t))*d2r,
                "lon": float(lon_interp(t))*d2r,
                "alt": float(alt_interp(t)),
                "vn": float(vn_interp(t)),
                "ve": float(ve_interp(t)),
                "vd": float(vd_interp(t)),
                "phi": phi,
                "the": the,
                "psi": psi,
                "psix": math.cos(psi),
                "psiy": math.sin(psi),
                "p_bias": 0,
                "q_bias": 0,
                "r_bias": 0,
                "ax_bias": 0,
                "ay_bias": 0,
                "az_bias": 0
            }
            result["filter"].append(nav)

    d = get_section(data, "vehicle_attitude_setpoint", 0)
    if d is not None:
        for i in range(len(d.data["timestamp"])):
            t = d.data["timestamp"][i]
            ap = {
                "time": t / 1e6,
                "hdg": d.data["yaw_body"][i],
                "roll": d.data["roll_body"][i],
                "pitch": d.data["pitch_body"][i],
                "alt": 0,
                "speed": 0
            }
            result["ap"].append(ap)

    d = get_section(data, "actuator_outputs", 0)
    if d is not None:
        for i in range(len(d.data["timestamp"])):
            t = d.data["timestamp"][i]
            act = {
                "time": t / 1e6,
                "aileron": (d.data["output[0]"][i] - 1500) / 500,
                "elevator": (d.data["output[1]"][i] - 1500) / 500,
                "throttle": (d.data["output[2]"][i] - 1000) / 1000,
                "rudder": -(d.data["output[3]"][i] - 1500) / 500
            }
            result["act"].append(act)

    return result
