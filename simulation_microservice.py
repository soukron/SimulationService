import requests
from time import time
from uuid import uuid4
import numpy as np
import re
import os
import openai
from time import time,sleep


embedding_service_host=os.getenv('EMBEDDING_SERVICE_HOST', '127.0.0.1')
embedding_service_port=os.getenv('EMBEDDING_SERVICE_PORT', '999')
nexus_service_host=os.getenv('NEXUS_SERVICE_HOST', '127.0.0.1')
nexus_service_port=os.getenv('NEXUS_SERVICE_PORT', '8888')


def wait_for_service(service_name, service_port):
    while True:
        try:
            return requests.get('http://' + service_name + ':' + service_port)
        except requests.exceptions.ConnectionError:
            print('Waiting for ' + service_name + ' to be reachable...')
            sleep(10)


def open_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as infile:
        return infile.read()


def save_file(filepath, content):
    with open(filepath, 'w', encoding='utf-8') as outfile:
        outfile.write(content)


openai.api_key = open_file('openaiapikey.txt').rstrip()
scene_dir = 'scenes/'
service_name = 'sensor_simulation'
content_prefix = 'Sensory input scene: '
tempo = 30


def gpt3_completion(prompt, engine='text-davinci-002', temp=0.7, top_p=1.0, tokens=1000, freq_pen=0.0, pres_pen=0.0, stop=['asdfasdf', 'asdasdf']):
    max_retry = 5
    retry = 0
    prompt = prompt.encode(encoding='ASCII',errors='ignore').decode()
    while True:
        try:
            response = openai.Completion.create(
                engine=engine,
                prompt=prompt,
                temperature=temp,
                max_tokens=tokens,
                top_p=top_p,
                frequency_penalty=freq_pen,
                presence_penalty=pres_pen,
                stop=stop)
            text = response['choices'][0]['text'].strip()
            text = re.sub('\s+', ' ', text)
            filename = '%s_gpt3.txt' % time()
            save_file('gpt3_logs/%s' % filename, prompt + '\n\n==========\n\n' + text)
            return text
        except Exception as oops:
            retry += 1
            if retry >= max_retry:
                return "GPT3 error: %s" % oops
            print('Error communicating with OpenAI:', oops)
            sleep(1)


def get_embedding(payload):  # payload is a list of strings
    # payload example: ['bacon bacon bacon', 'ham ham ham']
    # response example:  [{'string': 'bacon bacon bacon', 'vector': '[1, 1 ... ]'}, {'string': 'ham ham ham', 'vector': '[1, 1 ... ]'}]
    # embedding is already rendered as a JSON-friendly string
    url = 'http://%s:%s' % (embedding_service_host, embedding_service_port)  # currently the USEv5 service, about 0.02 seconds per transaction!
    response = requests.request(method='POST', url=url, json=payload)
    return response.json()


def nexus_send(payload):  # REQUIRED: content
    url = 'http://%s:%s/add' % (nexus_service_host, nexus_service_port)
    payload['time'] = time()
    payload['uuid'] = str(uuid4())
    payload['content'] = content_prefix + payload['content']
    embeddings = get_embedding([payload['content']])
    payload['vector'] = embeddings[0]['vector']
    payload['service'] = service_name
    response = requests.request(method='POST', url=url, json=payload)
    print(response.text)


def nexus_search(payload):
    url = 'http://%s:%s/search' % (nexus_service_host, nexus_service_port)
    response = requests.request(method='POST', url=url, json=payload)
    return response.json()


def nexus_bound(payload):
    url = 'http://%s:%s/bound' % (nexus_service_host, nexus_service_port)
    response = requests.request(method='POST', url=url, json=payload)
    #print(response)
    return response.json()


def nexus_save():
    url = 'http://%s:%s/save' % (nexus_service_host, nexus_service_port)
    response = requests.request(method='POST', url=url)
    print(response.text)


def find_actions(memories):
    for m in memories:
        if m['service'] == 'executive_action':
            return m['content']
    return None  # no actions detected in memories


if __name__ == '__main__':
    wait_for_service(embedding_service_host, embedding_service_port)
    wait_for_service(nexus_service_host, nexus_service_port)

    new_scene = 'Two men are sitting at a stone chess table in Central Park. They are playing chess. The sun is shining and birds are singing. It is a summer day. Children are running and playing in the distance. Horns honking and the bustle of New York can be heard in the background.'
    backstory = new_scene
    while True:
        last_scene = new_scene
        # generate event
        prompt = open_file('prompt_event.txt').replace('<<SCENE>>', last_scene).replace('<<STORY>>', backstory).replace('<<RARITY>>', 'likely')
        event = gpt3_completion(prompt)
        filename = '%s_event.txt' % time()
        save_file(scene_dir + filename, event)
        nexus_send({'content': event})
        # incorporate actions from the nexus
        payload = {'lower_bound': time() - tempo, 'upper_bound': time()}
        memories = nexus_bound(payload)
        action = find_actions(memories)
        if action:
            event = event + '\nAction I will take: %s' % action
        print('\n\nEVENT:', event)
        # new scene
        prompt = open_file('prompt_scene.txt').replace('<<SCENE>>', last_scene).replace('<<EVENT>>', event).replace('<<STORY>>', backstory)
        new_scene = gpt3_completion(prompt)
        print('\n\nSCENE:', new_scene)
        # save scene
        filename = '%s_scene.txt' % time()
        save_file(scene_dir + filename, new_scene)
        nexus_send({'content': new_scene})
        # summarize backstory up to this point
        backstory = (backstory + ' ' + event + ' ' + new_scene).strip()
        prompt = open_file('prompt_concise_summary.txt').replace('<<STORY>>', backstory)
        backstory = gpt3_completion(prompt)
        print('\n\nBACKSTORY:', backstory)
        # wait
        sleep(tempo)
