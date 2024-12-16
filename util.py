import torch
from dataset import MUSDBDataset
from torch.utils.data import DataLoader
import numpy as np
import musdb


def save_checkpoint(state, filename="my_checkpoint.pth.tar"):
    print("=> Saving checkpoint")
    torch.save(state, filename)


def load_checkpoint(checkpoint, model):
    print("=> Loading checkpoint")
    model.load_state_dict(checkpoint["state_dict"])


def get_loaders(
    musdb_dir,
    batch_size,
    transform,
    device,
    num_workers=4,
    pin_memory=True,
):
    train_musdataset = musdb.DB(musdb_dir, subsets='train',
                                split='train', download=False)

    valid_musdataset = musdb.DB(musdb_dir, subsets='train',
                                split='valid', download=False)

    train_ds = MUSDBDataset(
        mdataset=train_musdataset,
        transform=transform,
        device=device
    )

    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        num_workers=num_workers,
        pin_memory=pin_memory,
        shuffle=True,
    )

    val_ds = MUSDBDataset(
        mdataset=valid_musdataset,
        transform=transform,
        device=device
    )

    val_loader = DataLoader(
        val_ds,
        batch_size=batch_size,
        num_workers=num_workers,
        pin_memory=pin_memory,
        shuffle=False,
    )

    return train_loader, val_loader


def check_accuracy(loader, model, device="cuda"):
    num_correct = 0
    num_pixels = 0
    dice_score = 0
    model.eval()

    with torch.no_grad():
        for x, y in loader:
            x = x.to(device)
            y = y.to(device)

            preds = torch.sigmoid(model(x))
            preds = (preds > 0.5).float()
            num_correct += (preds == y).sum()
            num_pixels += torch.numel(preds)
            dice_score += (2 * (preds * y).sum()) / (
                (preds + y).sum() + 1e-8
            )

    print(
        f"Got {num_correct}/{num_pixels} with acc {num_correct/num_pixels*100:.2f}")
    print(f"Dice score: {dice_score/len(loader)}")
    model.train()


def save_predictions(
    loader, model, folder="saved_spec/", device="cuda"
):
    model.eval()
    # Save as npy
    for idx, (x, y) in enumerate(loader):
        x = x.to(device=device)
        with torch.no_grad():
            preds = torch.sigmoid(model(x))
            preds = (preds > 0.5).float()
        preds = preds.numpy()
        np.save(
            f"{folder}/pred_{idx}", preds
        )
