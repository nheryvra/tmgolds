import requests
import base64
import time
import json
import os
import sys
import pprint
from datetime import datetime, timedelta
import zoneinfo

username = os.environ['TM_USER']
password = os.environ['TM_PASS']

basic_auth_token = base64.b64encode(bytes(f"{username}:{password}", encoding='utf-8')).decode('utf-8')

dedi_auth_endpoint = "https://prod.trackmania.core.nadeo.online/v2/authentication/token/basic"
dedi_auth_headers = { 'Content-Type': 'application/json' , 'Authorization': 'Basic %s'%basic_auth_token }
dedi_auth_body = { "audience": "NadeoLiveServices" }

dedi_auth_resp = requests.post(dedi_auth_endpoint, headers=dedi_auth_headers, json=dedi_auth_body)

if dedi_auth_resp.status_code == 200:
    accessToken = dedi_auth_resp.json()['accessToken']
    refreshToken = dedi_auth_resp.json()['refreshToken']
else:
    print("Ubi auth returned ", dedi_auth_resp.status_code )
    exit(1)


auth_header = { 'Authorization': "nadeo_v1 t=%s" % accessToken, 'User-Agent': 'https://nheryvra.github.io/tmgolds Estimating TOTD gold medals difficulty' }

months_of_backlog = 12
totd_endpoint = f"https://live-services.trackmania.nadeo.live/api/token/campaign/month?offset=0&length={months_of_backlog}&royal=0"
mapinfo_endpoint = "https://live-services.trackmania.nadeo.live/api/token/map/"

# camp_endpoint = " https://live-services.trackmania.nadeo.live/api/token/campaign/official?offset=0&length=1"

scores_endpoint = "https://live-services.trackmania.nadeo.live/api/token/leaderboard/group/map?"


def get_totd_uids(resp):
    uids = {}
    if resp.status_code == 200:
        for day in resp.json()['monthList'][0]['days']:
            if day['mapUid'] != '':
                uids[day['monthDay']] = day['mapUid']

    return uids

def get_camp_uids(resp):
    uids = {}
    if resp.status_code == 200:
        for day in resp.json()['campaignList'][0]['playlist']:
            if day['mapUid'] != '':
                uids[day['position']+1] = day['mapUid']

    return uids


def get_month_uids(month):
    uids = {}

    for day in month['days']:
        if day['mapUid'] != '':
            uids[day['monthDay']] = day['mapUid']

    return uids


def get_maps_info(uids):

    info = {}
    for d, uid in uids.items():

        time.sleep(1)
        print(f"Getting info on map {uid}... ", end='')

        map_resp = requests.get(mapinfo_endpoint + uid, headers=auth_header)

        print(map_resp.status_code, end='')

        if map_resp.status_code==200:
            info[d] = map_resp.json()

        print(" " + map_resp.json()['name'], end='')
        print("")

    return info


def get_score_positions(mapinfos, gold=True):
    body_maps = []
    scores_query = ""

    for day, mapinfo in mapinfos.items():

        score = mapinfo['goldTime'] if gold else 18000000 # 5 hours for last
        uid = mapinfo['uid']

        body_maps.append( { "mapUid" : uid, "groupUid": "Personal_Best" } )
        scores_query += f"scores[{uid}]={score}&"


    body = { "maps": body_maps }

    endpoint = scores_endpoint + scores_query

    resp = requests.post(endpoint, headers=auth_header, json=body)
    if resp.status_code == 200:
        return resp.json()
    else:
        print("score postitions returned ", resp.status_code)
        return []


def augment_with_pos(mapinfos, positions, gold=True):
    for pos in positions:
        pos_uid = pos['mapUid']
        rank = pos['zones'][0]['ranking']['position']
        keyname = "goldPosition" if gold else "lastPosition"

        for d, info in mapinfos.items():
            if info['uid'] == pos_uid:
                mapinfos[d][keyname] = rank

    return mapinfos

def add_gold_ratios(totd_info):
    for d, map in totd_info.items():
        if "goldPosition" in map and "lastPosition" in map:
            totd_info[d]["goldRatio"] = round(100*map["goldPosition"] / map['lastPosition'], 2)

    return totd_info

def get_maps_info_from_uids(totd_uids):

    totd_info = get_maps_info(totd_uids)
    print(totd_info)

    totd_goldpos = get_score_positions(totd_info)
    print(totd_goldpos)
    totd_info = augment_with_pos(totd_info, totd_goldpos )
    print(totd_info)

    totd_lastpos = get_score_positions(totd_info, gold=False)
    print(totd_lastpos)

    totd_info = augment_with_pos(totd_info, totd_lastpos, gold=False )

    totd_info = add_gold_ratios(totd_info)
    print(totd_info)

    return totd_info

def trackmania_full_info(month):

    totd_uids = get_month_uids(month)
    print(totd_uids)
    return get_maps_info_from_uids(totd_uids)


def get_old_data():

    try:
        with open('tmdata.js', 'r') as f:
            all_info_txt = f.read()

        all_info_json = all_info_txt.replace("var totd_full_info = ", "")

        return json.loads(all_info_json)
    except Exception as e:
        print(e)
        return []


if __name__ == "__main__":


    if len(sys.argv) > 1:
        uids = { i : sys.argv[i] for i in range(1, len(sys.argv)) }
        print(uids)
        maps_infos = get_maps_info_from_uids(uids)
        pprint.pprint(maps_infos)
        pprint.pprint({ m['name'] : m['goldRatio'] for d, m in maps_infos.items()})
        exit(0)


    current_month = datetime.now().month
    current_day = datetime.now().day
    previous_month = (datetime.now() - timedelta(days=28)).month

    old_data = get_old_data()


    totd_resp = requests.get(totd_endpoint, headers=auth_header)


    old_months = []

    for month in totd_resp.json()['monthList']:
        if month['month'] == current_month:
            to_refresh = month
        else:
            old_months.append(month)


    new_data = []

    refreshed_current_month = trackmania_full_info(to_refresh)

    timestamp = datetime.now(zoneinfo.ZoneInfo('CET')).strftime("%Y-%m-%d %H:%M %Z")

    new_data.append({"month": to_refresh['month'], "year": to_refresh['year'], 'updated_on': timestamp, "maps": refreshed_current_month})

    for month in old_months:
        found = False
        if current_day > 7 or month['month'] != previous_month:      # refresh previous month for the first week of the current month
            for info in old_data:
                if month['month'] == info['month'] and month['year'] == info['year']:
                    print("Using old data for month", month['month'])
                    found = True
                    new_data.append( info )

        if not found:
            print("getting api data for month", month['month'] )
            refreshed_month = trackmania_full_info(month)
            timestamp = datetime.now(zoneinfo.ZoneInfo('CET')).strftime("%Y-%m-%d %H:%M %Z")
            new_data.append({"month": month['month'], "year": month['year'], 'updated_on': timestamp, "maps": refreshed_month})


    with open("tmdata.js", "w") as f:
        f.write("var totd_full_info = " + json.dumps(new_data))
