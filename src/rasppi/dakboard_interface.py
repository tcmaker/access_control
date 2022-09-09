import requests
from urllib.parse import urlencode, quote_plus

class DakBoard:
    def __init__(self,apikey):
        self._apikey = apikey

    def get_blocks(self, screen_id, **kwargs):
        url = f"https://dakboard.com/api/2/screens/{screen_id}/blocks?api_key={self._apikey}"
        response = requests.request("GET",url)
        return response.json()


    def update_block(self, screen_id, block_id, **kwargs):
        url = f"https://dakboard.com/api/2/screens/{screen_id}/blocks/{block_id}?api_key={self._apikey}"
        payload = urlencode(kwargs,quote_via=quote_plus)
        requests.request("PUT",url,headers={},data=payload)


if __name__ == "__main__":
    board = DakBoard("cabcee0aa846d3cc62cabbbb715b45bd")

    blocks = board.get_blocks("scr_92b9c3810c1e")
    print(blocks)
    text = [b for b in blocks if b['name'] == 'MyText'][0]
    shapered = [b for b in blocks if b['name'] == 'redshape'][0]
    print(f"BlockId is {text['id']}")

    board.update_block("scr_92b9c3810c1e", shapered['id'], is_disabled=0)
    #board.update_block("scr_92b9c3810c1e", text['id'], text=" ")
    #exit(0)
    board.update_block("scr_92b9c3810c1e", text['id'], text=

"""<img src="http://robertdahlstrom.com/lakehelen.jpg" width="70%" height="70%">
Test of image
""")
#![Awesome](http://robertdahlstrom.com/lakehelen.jpg "Lake Helen")


