import requests
import datetime
import time
import winsound
import sys, msvcrt, tabulate, json, copy, argparse, os
from hashlib import sha256
from collections import Counter
from math import sin, cos, sqrt, atan2, radians

CALENDAR_URL = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/calendarByDistrict?district_id={0}&date={1}"
BOOKING_URL = "https://cdn-api.co-vin.in/api/v2/appointment/schedule"
BENEFICIARIES_URL = "https://cdn-api.co-vin.in/api/v2/appointment/beneficiaries"
WARNING_BEEP_DURATION = (1000, 2000)

with open('./data/geocode_IN.json') as f:
    data = json.load(f)

PIN_lat = data[0]
PIN_long = data[1]


def beep(freq, duration):
    winsound.Beep(freq, duration)


def display_table(dict_list):
    '''
    This function
        1. Takes a list of dictionary
        2. Add an Index column, and
        3. Displays the data in tabular format
    '''
    header = ['idx'] + list(dict_list[0].keys())
    rows = [[idx + 1] + list(x.values()) for idx, x in enumerate(dict_list)]
    print(tabulate.tabulate(rows, header, tablefmt='grid'))


class TimeoutExpired(Exception):
    pass


def calc_haversine_distance(lat1, lon1, lat2, lon2):
    """
    This function calculates the haversine distance between two points
    :param lat1:
    :param lon1:
    :param lat2:
    :param lon2:
    :return:
    """

    # approximate radius of earth in km
    R = 6373.0

    lat1 = radians(float(lat1))
    lat2 = radians(float(lat2))
    lon1 = radians(float(lon1))
    lon2 = radians(float(lon2))

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c

    return distance


def check_calendar(request_header, vaccine_type, district_dtls, minimum_slots, min_age_booking, lat, long):
    '''
    This function
        1. Takes details required to check vaccination calendar
        2. Filters result by minimum number of slots available
        3. Returns False if token is invalid
        4. Returns list of vaccination centers & slots if available
    '''

    # if latitude and longitude are not available for distance calc, then plugging in center of India
    if lat is None:
        lat = 20.5937
    if long is None:
        long = 78.9629

    try:
        print('===================================================================================')
        today = datetime.datetime.today()
        tomorrow = (today + datetime.timedelta(days=1)).strftime("%d-%m-%Y")

        CALENDAR_URL = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/calendarByDistrict?district_id={0}&date={1}"

        if vaccine_type:
            CALENDAR_URL += f"&vaccine={vaccine_type}"

        options = []
        for district in district_dtls:
            resp = requests.get(CALENDAR_URL.format(district['district_id'], tomorrow), headers=request_header)

            if resp.status_code == 401:
                print('TOKEN INVALID')
                return False

            elif resp.status_code == 200:
                resp = resp.json()
                print(f"Centers available in {district['district_name']} from {tomorrow} as of {today.strftime('%Y-%m-%d %H:%M:%S')}: {len(resp['centers'])}")

                if len(resp['centers']) >= 0:
                    for center in resp['centers']:
                        for session in center['sessions']:
                            if (session['available_capacity'] >= minimum_slots) and (session['min_age_limit'] <= min_age_booking):
                                out = {}
                                out['name'] = center['name']
                                out['district'] = center['district_name']
                                out['center_id'] = center['center_id']
                                out['available'] = session['available_capacity']
                                out['date'] = session['date']
                                out['slots'] = session['slots']
                                out['session_id'] = session['session_id']
                                out['min_age_limit'] = session['min_age_limit']

                                if isinstance(center['lat'], float):
                                    center_lat = center['lat']
                                    center_long = center['long']
                                else:
                                    center_PIN = center['pincode']
                                    center_lat = PIN_lat.get(str(center_PIN))
                                    center_long = PIN_long.get(str(center_PIN))

                                distance = calc_haversine_distance(lat, long, center_lat, center_long)
                                out['distance'] = distance
                                options.append(out)

                            else:
                                pass

                else:
                    pass
            else:
                pass

        for dist in set([item['district'] for item in options]):
            for district in district_dtls:
                if dist == district['district_name']:
                    for _ in range(2):
                        # beep twice for each district with a slot
                        beep(district['district_alert_freq'], 150)

        return options

    except Exception as e:
        print(str(e))
        beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])


def book_appointment(request_header, details):
    '''
    This function
        1. Takes details in json format
        2. Attempts to book an appointment using the details
        3. Returns True or False depending on Token Validity
    '''
    try:
        print('================================= ATTEMPTING BOOKING ==================================================')

        resp = requests.post(BOOKING_URL, headers=request_header, json=details)
        print(f'Booking Response Code: {resp.status_code}')
        print(f'Booking Response : {resp.text}')

        if resp.status_code == 401:
            print('TOKEN INVALID')
            return False

        elif resp.status_code == 200:
            beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])
            print('##############    BOOKED!  ##############')
            os.system("pause")

        else:
            print(f'Response: {resp.status_code} : {resp.text}')
            os.system("pause")
            return True

    except Exception as e:
        print(str(e))
        beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])


def input_with_timeout(prompt, timeout, timer=time.monotonic):
    '''
    This function gives option to provide an input but on a timer
    '''
    sys.stdout.write(prompt)
    sys.stdout.flush()
    endtime = timer() + timeout
    result = []
    while timer() < endtime:
        if msvcrt.kbhit():
            result.append(msvcrt.getwche()) #XXX can it block on multibyte characters?
            if result[-1] == '\r':
                return ''.join(result[:-1])
        time.sleep(0.04) # just to yield to other processes/threads
    raise TimeoutExpired


def check_and_book(request_header, vaccine_type, beneficiary_dtls, district_dtls, minimum_slots, min_age_booking,
                   autobook=False, lat=None, long=None):
    '''
    This function
        1. Checks the vaccination calendar for available slots,
        2. Lists all viable options,
        3. Takes user's choice of vaccination center and slot,
        4. Calls function to book appointment, and
        5. Returns True or False depending on Token Validity
    '''

    if autobook:
        if lat is None:
            raise ValueError("Latitude and Longitude have to be defined for autobook")
        elif long is None:
            raise ValueError("Latitude and Longitude have to be defined for autobook")

    try:
        options = check_calendar(request_header, vaccine_type, district_dtls, minimum_slots, min_age_booking, lat, long)

        if isinstance(options, bool):
            return False

        options = sorted(options, key=lambda k: (
        k['distance'], datetime.datetime.strptime(k['date'], "%d-%m-%Y"), k['name'].lower()))

        tmp_options = copy.deepcopy(options)
        if len(tmp_options) > 0:
            cleaned_options_for_display = []
            for item in tmp_options:
                item.pop('session_id', None)
                item.pop('center_id', None)
                item.pop('distance', None)
                item.pop('min_age_limit', None)
                cleaned_options_for_display.append(item)

            display_table(cleaned_options_for_display)
            if autobook:
                choice = "1.1"
            else:
                choice = input_with_timeout(
                    '----------> Wait 10 seconds for updated options OR \n----------> Enter a choice e.g: 1.4 for (1st center 4th slot): ',
                    10)

        else:
            for i in range(15, 0, -1):
                msg = f"No viable options. Next update in {i} seconds.."
                print(msg, end="\r", flush=True)
                sys.stdout.flush()
                time.sleep(1)
            choice = '.'


    except TimeoutExpired:
        time.sleep(15)
        return True

    else:
        if choice == '.':
            return True
        else:
            choice = choice.split('.')
            choice = [int(item) for item in choice]
            print(f'============> Got {choice}')

            new_req = {}
            beneficiaries = [beneficiary['beneficiary_reference_id'] for beneficiary in beneficiary_dtls]
            new_req['beneficiaries'] = beneficiaries                             # pass list of beneficiaries
            new_req['dose'] = 2 if vaccine_type else 1                           # if vaccine type is available, then its their second dose
            new_req['center_id'] = options[choice[0] - 1]['center_id']
            new_req['session_id'] = options[choice[0] - 1]['session_id']
            new_req['slot'] = options[int(choice[0]) - 1]['slots'][choice[1] - 1]
            print(f'Booking with info: {new_req}')

            return book_appointment(request_header, new_req)


def get_districts(request_header):
    '''
    This function
        1. Lists all states, prompts to select one,
        2. Lists all districts in that state, prompts to select required ones, and
        3. Returns the list of districts as list(dict)
    '''
    states = requests.get('https://cdn-api.co-vin.in/api/v2/admin/location/states')

    state = None
    if states.status_code == 200:
        states = states.json()['states']

        refined_states = []
        for state in states:
            tmp = {}
            tmp['state'] = state['state_name']
            refined_states.append(tmp)

        display_table(refined_states)

        state = int(input('Enter State index: '))
        state_id = states[state - 1]['state_id']

    else:
        print('Unable to fetch states')
        print(states.status_code)
        print(states.text)
        os.system("pause")

    districts = requests.get(f'https://cdn-api.co-vin.in/api/v2/admin/location/districts/{state_id}')
    if districts.status_code == 200:
        districts = districts.json()['districts']

        refined_districts = []
        for district in districts:
            tmp = {}
            tmp['district'] = district['district_name']
            refined_districts.append(tmp)

        display_table(refined_districts)
        reqd_districts = input('Enter comma separated index numbers of districts to monitor : ')
        districts_idx = [int(idx) -1 for idx in reqd_districts.split(',')]
        reqd_districts = [{
            'district_id': item['district_id'],
            'district_name': item['district_name'],
            'district_alert_freq': 440 + ((2 * idx) * 110)
            } for idx, item in enumerate(districts) if idx in districts_idx]

        print(f'Selected districts: ')
        display_table(reqd_districts)
        return reqd_districts


    else:
        print('Unable to fetch districts')
        print(districts.status_code)
        print(districts.text)
        os.system("pause")


def get_beneficiaries(request_header):
    '''
    This function
        1. Fetches all beneficiaries registered under the mobile number,
        2. Prompts user to select the applicable beneficiaries, and
        3. Returns the list of beneficiaries as list(dict)
    '''
    beneficiaries = requests.get(BENEFICIARIES_URL, headers=request_header)

    if beneficiaries.status_code == 200:
        beneficiaries = beneficiaries.json()['beneficiaries']

        refined_beneficiaries = []
        for beneficiary in beneficiaries:
            beneficiary['age'] = datetime.datetime.today().year - int(beneficiary['birth_year'])

            tmp = {}
            tmp['beneficiary_reference_id'] = beneficiary['beneficiary_reference_id']
            tmp['name'] = beneficiary['name']
            tmp['vaccine'] = beneficiary['vaccine']
            tmp['age'] = beneficiary['age']
            refined_beneficiaries.append(tmp)

        display_table(refined_beneficiaries)
        print("""
        ################# IMPORTANT NOTES #################
        # 1. While selecting beneficiaries, make sure that selected beneficiaries are all taking the same dose: either first OR second.
        #    Please do no try to club together booking for first dose for one beneficiary and second dose for another beneficiary.
        #
        # 2. While selecting beneficiaries, also make sure that beneficiaries selected for second dose are all taking the same vaccine: COVISHIELD OR COVAXIN.
        #    Please do no try to club together booking for beneficiary taking COVISHIELD with beneficiary taking COVAXIN.
        #
        # 3. If you're selecting multiple beneficiaries, make sure all are of the same age group (45+ or 18+) as defined by the govt.
        #    Please do not try to club together booking for younger and older beneficiaries.
        ###################################################
        """)
        reqd_beneficiaries = input('Enter comma separated index numbers of beneficiaries to book for : ')
        beneficiary_idx = [int(idx) -1 for idx in reqd_beneficiaries.split(',')]
        reqd_beneficiaries = [{
            'beneficiary_reference_id': item['beneficiary_reference_id'],
            'vaccine': item['vaccine'], 'age' : item['age']
            } for idx, item in enumerate(beneficiaries) if idx in beneficiary_idx]


        print(f'Selected beneficiaries: ')
        display_table(reqd_beneficiaries)
        return reqd_beneficiaries

    else:
        print('Unable to fetch beneficiaries')
        print(beneficiaries.status_code)
        print(beneficiaries.text)
        os.system("pause")


def get_min_age(beneficiary_dtls):
    """
    This function returns a min age argument, based on age of all beneficiaries
    :param beneficiaries:
    :return: min_age:int
    """
    age_list = [item['age'] for item in beneficiary_dtls]
    min_age = min(age_list)
    return min_age


def generate_token_OTP(mobile):
    """
    This function generate OTP and returns a new token
    """
    data = {"mobile": mobile, "secret": "U2FsdGVkX1/3I5UgN1RozGJtexc1kfsaCKPadSux9LY+cVUADlIDuKn0wCN+Y8iB4ceu6gFxNQ5cCfjm1BsmRQ=="}
    print(f"Requesting OTP with mobile number {mobile}..")
    txnId = requests.post(url='https://cdn-api.co-vin.in/api/v2/auth/generateMobileOTP', json=data)

    if txnId.status_code == 200:
        txnId = txnId.json()['txnId']
    else:
        print('Unable to Create OTP')
        print(txnId.text)
        os.system("pause")

    OTP = input("Enter OTP: ")
    data = {"otp": sha256(str(OTP).encode('utf-8')).hexdigest(), "txnId": txnId}
    print(f"Validating OTP..")

    token = requests.post(url='https://cdn-api.co-vin.in/api/v2/auth/validateMobileOtp', json=data)
    if token.status_code == 200:
        token = token.json()['token']
    else:
        print('Unable to Validate OTP')
        print(token.text)
        os.system("pause")

    print(f'Token Generated: {token}')
    return token


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--token', help='Pass token directly')
    parser.add_argument('--lat', default=None, help='Latitude of your location')
    parser.add_argument('--long', default=None, help='Longitude of your location')
    parser.add_argument('--PINCode', default=None, help='PIN Code of your location')
    parser.add_argument('--book', action='store_true', help='Experimental flag - not used')

    args = parser.parse_args()

    token = None
    try:
        if args.token:
            token = args.token
        else:
            mobile = input("Enter the registered mobile number: ")
            token = generate_token_OTP(mobile)

        if (args.lat is not None) and (args.long is not None):
            lat = args.lat
            long = args.long
        elif args.PINCode is not None:
            lat = PIN_lat.get(str(args.PINCode))
            long = PIN_long.get(str(args.PINCode))

        else:
            lat = None
            long = None

        request_header = {"Authorization": f"Bearer {token}"}

        # Get Beneficiaries
        print("Fetching registered beneficiaries.. ")
        beneficiary_dtls = get_beneficiaries(request_header)

        if len(beneficiary_dtls) == 0:
            print("There should be at least one beneficiary. Exiting.")
            os.system("pause")
            sys.exit(1)

        min_age_booking = get_min_age(beneficiary_dtls)

        # Make sure all beneficiaries have the same type of vaccine
        vaccine_types = [beneficiary['vaccine'] for beneficiary in beneficiary_dtls]
        vaccines = Counter(vaccine_types)

        if len(vaccines.keys()) != 1:
            print(f"All beneficiaries in one attempt should have the same vaccine type. Found {len(vaccines.keys())}")
            os.system("pause")
            sys.exit(1)


        vaccine_type = vaccine_types[0]

        # Collect vaccination center preferance
        district_dtls = get_districts(request_header)

        # Set filter condition
        minimum_slots = int(input('Filter out centers with availability less than: '))
        minimum_slots = minimum_slots if minimum_slots > len(beneficiary_dtls) else len(beneficiary_dtls)

        TOKEN_VALID = True
        while TOKEN_VALID:
            request_header = {"Authorization": f"Bearer {token}"}

            # call function to check and book slots
            TOKEN_VALID = check_and_book(request_header, vaccine_type, beneficiary_dtls, district_dtls, minimum_slots,
                                         min_age_booking, args.book, lat, long)

            # check if token is still valid
            beneficiaries_list = requests.get(BENEFICIARIES_URL, headers=request_header)
            if beneficiaries_list.status_code == 200:
                TOKEN_VALID = True

            else:
                # if token invalid, regenerate OTP and new token
                beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])
                print('Token is INVALID.')
                TOKEN_VALID = False

                tryOTP = input('Try for a new Token? (y/n): ')
                if tryOTP.lower() == 'y':
                    if mobile:
                        tryOTP = input(f"Try for OTP with mobile number {mobile}? (y/n) : ")
                        if tryOTP.lower() == 'y':
                            token = generate_token_OTP(mobile)
                            TOKEN_VALID = True
                        else:
                            TOKEN_VALID = False
                            print("Exiting")
                    else:
                        mobile = input(f"Enter 10 digit mobile number for new OTP generation? : ")
                        token = generate_token_OTP(mobile)
                        TOKEN_VALID = True
                else:
                    print("Exiting")
                    os.system("pause")

    except Exception as e:
        print(str(e))
        print('Exiting Script')
        os.system("pause")

if __name__ == '__main__':
    main()
