import time

import torch
import torch.nn as nn
import torch.optim as optim
import random
from tqdm import tqdm

import transforms
from model import UNET
from util import (batch_normalized, get_loaders, load_checkpoint,
                  save_checkpoint, save_predictions)
from torch.optim.lr_scheduler import ReduceLROnPlateau

# Hyperparameters etc.
LEARNING_RATE = 1e-4
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
BATCH_SIZE = 4
NUM_EPOCHS = 20
NUM_WORKERS = 16
CHANNELS = 2
N_FFT = 1024  # HEIGHT
N_HOPS = 512  # WIDTH
PIN_MEMORY = False
LOAD_MODEL = False

""" 
Train code has been inspired by:
https://github.com/aladdinpersson/Machine-Learning-Collection/blob/558557c7989f0b10fee6e8d8f953d7269ae43d4f/ML/Pytorch/image_segmentation/semantic_segmentation_unet/train.py
"""

def validate_model(loader, encoder, model, loss_fn):
    model.eval()
    val_loss = 0
    total_samples = 0
    
    val_bar = tqdm(loader, desc="Validation")

    with torch.no_grad():
        for batch_idx, (data, targets) in enumerate(tqdm(val_bar)):
            data, targets = data.to(DEVICE), targets.to(DEVICE)
            data = encoder(data)
            data_normalized, _, _ = batch_normalized(data)
            predictions = model(data_normalized)
            targets = encoder(targets)
            targets_normalized, _, _ = batch_normalized(targets)
            loss = loss_fn(predictions, targets_normalized)

            batch_size = data.size(0)
            val_loss += loss.item() * batch_size
            total_samples += batch_size

            val_bar.set_postfix(
                loss=loss.item(),
                avg_loss=f"{val_loss/total_samples:.4f}") 
    return val_loss / total_samples

def train_fn(loader, encoder, model, optimizer, loss_fn, scaler):
    model.train()
    train_loss = 0
    total_samples = 0

    train_bar = tqdm(loader, desc="Training")

    for batch_idx, (data, targets) in enumerate(train_bar):
        data = data.to(device=DEVICE)
        targets = targets.to(device=DEVICE)


        # forward
        with torch.amp.autocast(DEVICE):
            data = encoder(data)
            data_normalized, _, _ = batch_normalized(data)
            predictions = model(data_normalized)
            targets = encoder(targets)
            targets_normalized, _, _ = batch_normalized(targets)
            loss = loss_fn(predictions, targets_normalized)

        # backward
        optimizer.zero_grad()
        scaler.scale(loss).backward()
        
        # gradient clipping
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        
        scaler.step(optimizer)
        scaler.update()
        
        batch_size = data.size(0)
        train_loss += loss.item() * batch_size
        total_samples += batch_size

        # update tqdm loop
        train_bar.set_postfix(
            loss=loss.item(),
            avg_loss=f"{train_loss/total_samples:.4f}",
            lr=f"{optimizer.param_groups[0]['lr']:.2E}")
        
    return train_loss / total_samples


def main():
    model = UNET().to(DEVICE)
    # dp_model = nn.DataParallel(model).to(DEVICE)
    loss_fn = nn.MSELoss().to(DEVICE)
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    scheduler = ReduceLROnPlateau(optimizer, mode="min", patience=2)

    train_loader, val_loader = get_loaders(
        musdb_dir='./musdb',
        batch_size=BATCH_SIZE,
        num_workers=NUM_WORKERS,
        pin_memory=PIN_MEMORY,
    )
    stft, istft = transforms.make_filterbanks(
        n_fft=N_FFT, hop_length=N_HOPS
    )
    encoder = stft

    if LOAD_MODEL:
        load_checkpoint(torch.load("my_checkpoint.pth.tar"), model)

    scaler = torch.amp.GradScaler(DEVICE)
    best_loss = float('inf')
    patience = 5
    count = 0

    for epoch in range(NUM_EPOCHS):
        random.seed(epoch)
        train_fn(loader=train_loader,
                 model=model,
                 encoder=encoder,
                 optimizer=optimizer,
                 loss_fn=loss_fn,
                 scaler=scaler)

        val_loss = validate_model(loader=val_loader,
                                  encoder=encoder,
                                  model=model,
                                  loss_fn=loss_fn)
        print(f"Average Val Loss:{val_loss}")
        scheduler.step(val_loss)

        if val_loss < best_loss:
            # save model
            checkpoint = {
                "state_dict": model.state_dict(),
                "optimizer": optimizer.state_dict()
            }
            best_loss = val_loss
            filename = f"my_checkpoint_{epoch}.pth"
            save_checkpoint(checkpoint, filename)
            folder= f'saved_spectrograms/{epoch}'
            save_predictions(val_loader, model, encoder=encoder, folder=folder, device='cuda')
        else:
            count += 1
            if count > patience:
                break

if __name__ == "__main__":
    main()
