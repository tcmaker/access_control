import requests

class TCMakerMembership:
    def __init__(self):
        #self.url = 'https://members.tcmaker.org/api/v1/keyfobs/' #TODO: setup via config
        self.base_url = 'http://127.0.0.1:8000/api/v1/'
        self.api_key = 'boguskey'
        self.RequestHeaders = {
                    # Generate an API token from the admin panel
                    #
                    'Authorization': 'Bearer %s' %  (self.api_key),
                    'Content-Type' : 'application/json'
                }

    def list_keyfobs(self, code=None):
        query = f'?code={code}' if code is not None else ""
        return self.list_models(self.base_url + 'keyfobs/' + query)

    def list_persons(self):
        return self.list_models('https://members.tcmaker.org/api/v1/persons/')

    def list_models(self, start_url):
        url = start_url
        while url is not None:
            # Fetch the first page
            response = requests.get(url, headers=self.RequestHeaders)
            # Raise an exception on HTTP error
            response.raise_for_status()
            # Parse the JSON in the response into Python data structures
            body = response.json()
            # Update the loop for the next page
            url = body['next']
            # Loop over this page of results
            for result in body['results']:
                yield result

    def get_person(self,person_uuid=None, url=None):
        url = f'https://members.tcmaker.org/api/v1/persons/{person_uuid}/' if url is None else url
        response = requests.get(url, headers=self.RequestHeaders)
        # Raise an exception on HTTP error
        response.raise_for_status()
        # Parse the JSON in the response into Python data structures
        body = response.json()
        return body

    def get_household(self, household_uuid=None, url=None):
        url = f'https://members.tcmaker.org/api/v1/households/{household_uuid}/' if url is None else url
        response = requests.get(url, headers=self.RequestHeaders)
        # Raise an exception on HTTP error
        response.raise_for_status()
        # Parse the JSON in the response into Python data structures
        body = response.json()
        return body

if __name__ == "__main__":
    from time import perf_counter
    start = perf_counter()
    tcm = TCMakerMembership()
    #print(next(tcm.list_keyfobs(tcm.url)))
    #print([t for t in tcm.list_models('https://members.tcmaker.org/api/v1/persons/') if t.get('family_name','') == "Aellen"])
    #for t in tcm.list_keyfobs():
    #    if t.get("family_name","") == "Dahlstrom":
    #        print(t)
    #        break
    #person = tcm.get_person('ce7976b2-6c7b-4460-b99a-d501b83e4c53')
    #household = tcm.get_household(url=person['administered_households'][0]['url'])
    #print(f"Status: {household['status']}")
    #print(f"Status: {person['status']}")
    fobs = tcm.list_keyfobs(code='12345678')
    #print(f"Matches: {len(list(fobs))}")
    for fob in fobs:
        print(f"  Fob: {fob['code']}")
        print(f"       Person: {fob['person']}")
        print(f"      Access?: {fob['is_membership_valid']}")
    #person = tcm.get_person('ce7976b2-6c7b-4460-b99a-d501b83e4c53')
    #end = perf_counter()
    #status = person['administered_households'][0]['status']
    #mail = person['email']
    #phone = person['phone_number']
    #print(f"Status: {status}, query took {end-start} seconds")
    #print(f"  Mail: {mail}")
    #print(f" Phone: {phone}")

