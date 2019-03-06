"""Train LM"""

import argparse
import math
import random
import sys
import time

import torch

from paths import LOG_HOME
from paths import MODELS_HOME
from utils import generate_vocab_mappings, load_WordNLM_model
from train_data_functions import prepare_dataset_chunks
from model import WordNLM
import corpusIteratorWikiWords

CHAR_VOCABS = {"german": "vocabularies/german-wiki-word-vocab-50000.txt",
                   "italian": "vocabularies/italian-wiki-word-vocab-50000.txt",
                   "english": "vocabularies/english-wiki-word-vocab-50000.txt"}

def get_args(*input_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", dest="language", type=str)
    parser.add_argument("--load-from", dest="load_from", type=str)
    parser.add_argument("--save-to", dest="save_to", type=str)
    parser.add_argument("--batchSize", type=int, default=random.choice([128, 128, 128, 256]))
    parser.add_argument("--char_embedding_size", type=int, default=random.choice([100, 200, 200, 300, 300, 300, 300, 1024]))
    parser.add_argument("--hidden_dim", type=int, default=random.choice([1024]))
    parser.add_argument("--layer_num", type=int, default=random.choice([1, 2]))
    parser.add_argument("--weight_dropout_in", type=float, default=random.choice([0.0, 0.0, 0.0, 0.01]))
    parser.add_argument("--weight_dropout_hidden", type=float, default=random.choice([0.0, 0.05, 0.15, 0.2]))
    parser.add_argument("--char_dropout_prob", type=float, default=random.choice([0.0, 0.0, 0.001, 0.01, 0.01]))
    parser.add_argument("--char_noise_prob", type = float, default=random.choice([0.0, 0.0]))
    parser.add_argument("--learning_rate", type = float, default= random.choice([0.6, 0.7, 0.8, 0.9, 1.0,1.0,  1.1, 1.1, 1.2, 1.2, 1.2, 1.2, 1.3, 1.3, 1.4, 1.5, 1.6]))
    parser.add_argument("--myID", type=int, default=random.randint(0,1000000000))
    parser.add_argument("--sequence_length", type=int, default=random.choice([50]))
    parser.add_argument("--verbose", type=bool, default=False)
    parser.add_argument("--lr_decay", type=float, default=random.choice([0.7, 0.9, 0.95, 0.98, 0.98, 1.0]))

    args=parser.parse_args()


    if "MYID" in args.save_to:
        args.save_to = args.save_to.replace("MYID", str(args.myID))

    print(args)
    return args

def plus(it1, it2):
    for x in it1:
        yield x
    for x in it2:
        yield x

# FIXME: WTF, use the forward from the model
def front_pass(numeric, train=True, printHere=False):
    global hidden
    global beginning  # FIXME: WTF globals
    if hidden is None or (train and random.random() > 0.9):
        hidden = None
        beginning = zeroBeginning
    elif hidden is not None:
        hidden = tuple([Variable(x.data).detach() for x in hidden])

    numeric = torch.cat([beginning, numeric], dim=0).to(device=device)
    beginning = numeric[numeric.size()[0]-1].view(1, args.batchSize)

    input_tensor = numeric[:-1]
    target_tensor = numeric[1:]

    log_probs = model.forward(input_tensor)
    loss = train_loss(log_probs.view(-1, len(itos)+3), target_tensor.view(-1))

    if printHere:
        lossTensor = print_loss(log_probs.view(-1, len(itos)+3), target_tensor.view(-1)).view(-1, args.batchSize)
        losses = lossTensor.data.cpu().numpy()
        numericCPU = numeric.cpu().data.numpy()
        print(("NONE", itos[numericCPU[0][0]-3]))
        for i in range((args.sequence_length)):
            print((losses[i][0], itos[numericCPU[i+1][0]-3]))
    return loss, target_tensor.view(-1).size()[0]

def run_epoch_train(optim, model, corpus_iterator):
    optim.zero_grad()
    training_data = corpus_iterator.training(args.language)
    print("Got data, preparing dataset chunks")
    training_chars = prepare_dataset_chunks(training_data, train=True)

    start_time = time.time()
    train_chars = 0
    counter = 0
    hidden, beginning = None, None
    while True:
        counter += 1
        try:
            numeric = next(training_chars)
        except StopIteration:
            break

        print_here = (counter % 50 == 0)
        loss, char_counts = front_pass(numeric, printHere=print_here, train=True)
        loss.backward()
        torch.nn.utils.clip_grad_value_(parameters_cached, 5.0)
        optim.step()

        if loss > 15.0:
            loss_has_been_bad += 1
        else:
            loss_has_been_bad = 0
        if loss_has_been_bad > 100:
            print("Loss exploding, has been bad for a while")
            print(loss)
            quit()
        train_chars += char_counts
        if print_here:
            print("Loss here", loss)
            print(epoch,counter)
            print("Dev losses")
            print(devLosses)
            print("Chars per sec "+str(train_chars/(time.time()-start_time)))
            print(learning_rate)
            print(args)
        if counter % 20000 == 0: # and epoch == 0:
            if args.save_to is not None:
                save_path = MODELS_HOME+"/"+args.save_to+".pth.tar"
                torch.save(dict([(name, module.state_dict()) for name, module in named_modules.items()]), save_path)
        if (time.time() - total_start_time)/60 > 4200:
            print("Breaking early to get some result within 72 hours")
            total_start_time = time.time()
            break


def run_epoch_eval():
    dev_data = corpusIteratorWikiWords.dev(args.language)
    print("Got data")
    dev_chars = prepare_dataset_chunks(dev_data, train=False)

    dev_loss = 0
    dev_char_count = 0
    counter = 0
    hidden, beginning = None, None
    while True:
        counter += 1
        try:
            numeric = next(dev_chars)
        except StopIteration:
            break
        print_here = (counter % 50 == 0)
        loss, numberOfCharacters = front_pass(numeric, printHere=print_here, train=False)
        dev_loss += numberOfCharacters * loss.cpu().data.numpy()
        dev_char_count += numberOfCharacters
    devLosses.append(dev_loss/dev_char_count)
    print(devLosses)
    with open(LOG_HOME+"/"+args.language+"_"+__file__+"_"+str(args.myID), "w") as outFile:
        print(" ".join([str(x) for x in devLosses]), file=outFile)
        print(" ".join(sys.argv), file=outFile)
        print(str(args), file=outFile)
    if len(devLosses) > 1 and devLosses[-1] > devLosses[-2]:
        break
    if args.save_to is not None:
        torch.save(dict([(name, module.state_dict()) for name, module in named_modules.items()]), MODELS_HOME+"/"+args.save_to+".pth.tar")


def main():
    args = get_args()
    char_vocab_path = CHAR_VOCABS[args.language]
    itos, stoi = generate_vocab_mappings(char_vocab_path)
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    model = WordNLM(args.char_embedding_size, len(itos), args.hidden_dim, args.layer_num,
                    args.weight_dropout_in, args.weight_dropout_hidden, args.char_dropout_prob)
    model.to(device)
    model.train()
    train_loss = torch.nn.NLLLoss(ignore_index=0)
    print_loss = torch.nn.NLLLoss(reduction=None, ignore_index=0)

    if args.load_from is not None:
        checkpoint = torch.load(MODELS_HOME+args.load_from+".pth.tar")
        model = load_WordNLM_model(weight_path, model, device)

    # FIXME: Recuperer l'optimizer?
    optim = torch.optim.SGD(model.parameters(), lr=args.learning_rate, momentum=0.0)


    zero_beginning = torch.LongTensor([0 for _ in range(args.batchSize)]).to(device).view(1,args.batchSize)
    hidden = None
    beginning = None

    loss_has_been_bad = 0
    total_start_time = time.time()
    devLosses = []
    for epoch in range(10000):
        model.train()
        training_data = corpusIteratorWikiWords.training(args.language)
        print("Epoch: ", epoch)
        run_epoch_train() # FIXME: TODO

        model.eval()
        run_epoch_eval()  # FIXME: TODO

        # FIXME: Why is optimizer - Mention to dupoux
        # Momentum peut pas marcher si pas 0
        learning_rate = args.learning_rate * math.pow(args.lr_decay, len(devLosses))
        # FIXME: Pk cette ligne?
        optim = torch.optim.SGD(model.parameters(), lr=learning_rate, momentum=0.0) # 0.02, 0.9
