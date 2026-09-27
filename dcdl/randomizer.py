import random
from .models import Draw, DrawType

LETTER_COUNTS = {"A":57,"B":9,"C":18,"D":12,"E":98,"F":9,"G":9,"H":6,"I":57,"J":4,"K":3,"L":24,"M":18,"N":32,"O":48,"P":9,"Q":5,"R":44,"S":47,"T":36,"U":36,"V":6,"W":3,"X":3,"Y":4,"Z":3}
VOWELS=set("AEIOUY")
CONSONANT_DISTRIBUTION=([3,4,5,6,7],[.05,.20,.50,.20,.05])
NUMBER_POOL=[1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,25,50,75,100]

def _weighted_letter(chars, rng):
    return rng.choices(chars, weights=[LETTER_COUNTS[c] for c in chars], k=1)[0]

def generate_letters(count=10, required="", rng=None):
    rng=rng or random.Random(); required=[c for c in required.upper() if c in LETTER_COUNTS]
    nb_cons=rng.choices(*CONSONANT_DISTRIBUTION, k=1)[0]
    out=required[:count]
    cons=[c for c in LETTER_COUNTS if c not in VOWELS]; vows=list(VOWELS)
    while len(out)<count:
        current=sum(c not in VOWELS for c in out)
        out.append(_weighted_letter(cons if current<nb_cons else vows, rng))
    rng.shuffle(out)
    return Draw("".join(out), DrawType.LETTERS, out)

def generate_numbers(rng=None):
    rng=rng or random.Random(); pool=NUMBER_POOL.copy(); nums=[]
    for _ in range(6):
        x=rng.choice(pool); nums.append(str(x)); pool.remove(x)
    target=rng.randint(100,999)
    return Draw(f"{' '.join(nums)} / {target}", DrawType.NUMBERS, nums, target)

def generate_random(n, numbers_ratio=.25, letters_count=10, required="", seed=None):
    rng=random.Random(seed)
    return [generate_numbers(rng) if rng.random()<numbers_ratio else generate_letters(letters_count, required, rng) for _ in range(n)]
