from itertools import permutations, product

PAIR_PROMPT = r"""I will provide you with a base document and a set of other documents in JSON format. Your task is to determine which of the provided documents is most relevant to the base document and closer in terms of similarity and covering the main points discussed in the base document. The documents are educational in nature. 
The data will be in the following format:

base document text is :
{BASE_CONTENT}

----

{{
"candidate_1":{CANDIDATE_1_CONTENT},
"candidate_2":{CANDIDATE_2_CONTENT},
}}

The response should only contain candidate_1 or candidate_2 with no additional explanation or commentary. Identify the most relevant document.
"""

SYSTEM_PROMPT = "You are an intelligent assistant capable of evaluating the relevancy of passages. Given a base document and two candidate passages, determine which candidate is most similar to the base in terms of relevancy. Respond only with the ranking results, without any additional explanation or commentary."


class ThreeWayPairs:
    # create (base_accepted, accepted, rejected) pairs
    def __init__(self, accepted, rejected):
        self.accepted = accepted
        self.rejected = rejected
        self.accepted_pairs = list(permutations(self.accepted, 2))
        self.all_combinations = list(product(self.accepted_pairs, self.rejected))
        self.current_index = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.current_index >= len(self.all_combinations):
            raise StopIteration
        current_combination = self.all_combinations[self.current_index]
        self.current_index += 1
        return (*current_combination[0], current_combination[1])
