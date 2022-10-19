import itertools

notes = ['C','D','E','F','G','A','B']
nums = ['2','3','4','5','6','7']

allofthem = itertools.product(nums,notes)
notes = [y+x for x, y in allofthem]

def pitch(notename):
    if notename[0] == 'C':
        return 0
    if notename[0] == 'D':
        return 1
    if notename[0] == 'E':
        return 2
    if notename[0] == 'F':
        return 3
    if notename[0] == 'G':
        return 4
    if notename[0] == 'A':
        return 5
    if notename[0] == 'B':
        return 6

def octave(notename):
    return int(notename[1])

if __name__ == '__main__':
    for n in notes:
        nn = pitch(n) + octave(n) * 7
        print(f"{n}: {nn}")
    #print([pitch(n) + octave(n) * 8 for n in notes])



