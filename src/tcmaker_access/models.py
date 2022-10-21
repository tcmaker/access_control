from datetime import datetime

class Fob(): #ClubhouseFob? When wildapricot is made live
    def __init__(self, clubhouseJson):
        self.code = str(int(clubhouseJson['code']))
        self.user = clubhouseJson['person'].split('/')[-2]
        self.access_level = clubhouseJson['access_level']
        if clubhouseJson['membership_valid_through'] == None:
            self.expiration = datetime.min
        else:
            self.expiration = datetime.fromisoformat(clubhouseJson['membership_valid_through'])
        self.is_active = clubhouseJson['is_active']
        self.valid_membership = clubhouseJson['is_membership_valid']

    def expiration_timestamp(self):
        if self.expiration == datetime.min:
            return 0
        return self.expiration.timestamp()

    def esp_access(self):
        return 1 if (self.valid_membership and self.is_active) else 0

class ClubhouseFob(Fob):
    pass