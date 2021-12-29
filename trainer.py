<<<<<<< HEAD
from numpy.lib.function_base import average
from sklearn.utils import shuffle
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils import data
from torch.utils.data import DataLoader
from sklearn.metrics import f1_score, accuracy_score, confusion_matrix
import numpy as np
import pandas as pd
from tqdm import tqdm
from torch.utils.tensorboard import SummaryWriter
import os
from utils import *
from loss.ND_Crossentropy import CrossentropyND, TopKLoss
from loss.focalloss import *
from loss.label_smoothing import LabelSmoothingCrossEntropy
from utils import gpu_checking
from collections import defaultdict
import wandb

class TrainMaker:
    def __init__(self, args, model, data, data_v=None):
            self.args = args
            self.model = model
            self.data = data
            if data_v:
                self.data_v = data_v
            self.history = defaultdict(list)
            self.writer = SummaryWriter(log_dir='./runs/lr{}_wd{}'.format(self.args.lr, self.args.wd))
            
            self.optimizer = getattr(torch.optim, self.args.optimizer)
            self.optimizer = self.optimizer(self.model.parameters(), lr=self.args.lr, weight_decay=self.args.wd)

            # self.optimizer = self.args.optimizer
            # self.scheduler = optim.lr_scheduler.StepLR(self.optimizer, step_size=500, gamma=0.1)
            self.scheduler = self.__set_scheduler(args, self.optimizer)
            
            # criterion = getattr(torch.nn, self.criterion)
            self.criterion = self.__set_criterion(self.args.criterion)
            
            self.epoch = self.args.epoch
            self.lr = self.args.lr
            self.wd = self.args.wd
            self.channel_num = self.args.channel_num
            self.device = gpu_checking()
            self.history_mini_batch = defaultdict(list)
            # if args.mode == "train":
            #     self.trainer = self.__make_trainer(args=args,
            #                                         model=self.model,
            #                                         data=data,
            #                                         criterion=self.criterion,
            #                                         optimizer=self.optimizer)          

    def training(self, shuffle=True, interval=1000):
        prev_v = -10
        sampler = torch.utils.data.WeightedRandomSampler(self.data.in_weights, replacement=True, num_samples=self.args.batch_size)
        data_loader = DataLoader(self.data, batch_size=self.args.batch_size, sampler=sampler)

        # data_loader = DataLoader(self.data, batch_size=self.args.batch_size)
        # data_loader = self.data.data_loader_maker(self.args, shuffle, mode="train")

        for e in tqdm(range(self.epoch)):
            epoch_loss = 0
            self.model.train()

            pred_label_acc = None
            true_label_acc = None
            pred_list = None
            true_label = None
            # history_mini_batch = defaultdict(list)
            
            for idx, data in enumerate(data_loader): 
                x, y = data
               
                true_label = y.numpy()
                b = x.shape[0]

                self.optimizer.zero_grad() # optimizer 항상 초기화 
                #x = x.reshape(b,1,30,-1) ############## checking [1, 1, 30, 700] 미츼ㅣㅣ
                x = x.reshape(b, 1, self.channel_num, -1) # [1, 1, 25, 750]
                pred = self.model(x.to(device=self.device).float())
                
                pred_prob = F.softmax(pred, dim=-1) 
                # pred, (hidden_state, cell_state) = network(x.view(b, 1, -1).float().to(device=device), (hidden_state[:,:b].detach().contiguous(), cell_state[:,:b].detach().contiguous())) # view함수 -> 밑에 적음
                loss = self.criterion(pred_prob, y.flatten().long().to(device=self.device)) 
                if (idx+1) % interval == 0: print('[Epoch{}, Step({}/{})] Loss:{:.4f}'.format(e+1, idx+1, len(data_loader.dataset) // self.args.batch_size, epoch_loss / (idx + 1)))

                loss.backward()
                epoch_loss += loss.item()
                self.optimizer.step()
                
                pred_label = torch.argmax(pred_prob, dim=-1).cpu().numpy()
                # pred_list.append(pred_label) # pred_list에 prediction 넣어주기

                if pred_label_acc is None:
                    pred_label_acc = pred_label
                    true_label_acc = true_label
                else:
                    pred_label_acc = np.concatenate((pred_label_acc, pred_label), axis=None)
                    true_label_acc = np.concatenate((true_label_acc, true_label), axis=None)

                
                # Calculate log per mini-batch
                # log = calculate(self.args.metrics, loss, labels, outputs, acc_count=True)
                self.cal = Calculate()
                log = self.cal.calculator(metrics=self.args.metrics, loss=loss, y_true=y, y_pred=pred_label, acc_count=True)
                
                # Record history per mini-batch
                self.record_history(log, self.history_mini_batch, phase='train')

            # pred_list_acc = np.concatenate((pred_list_acc, pred_list))
            # print(pred_list_acc)
            
            # print("=====", true_label)
            # print("true_label:", true_label)
            # print(true_label)
            # print("\n\n\n", pred_list)
            # print(true_label_acc)
            # print(pred_label_acc)
           
            f1 = f1_score(true_label_acc, pred_label_acc, average='macro') 
            acc = accuracy_score(true_label_acc, pred_label_acc)
            cm = confusion_matrix(true_label_acc, pred_label_acc)
            epoch_loss = epoch_loss / (idx+1)
            
            # print('\nEpoch{} Training, f1:{:.4f}, acc:{:.4f}, Loss:{:.4f}'.format(e+1, f1, acc, epoch_loss))
            # print(cm) # confusion matrix print

            f1_v, acc_v, cm_v, loss_v = self.evaluation(self.data_v)
            if f1_v > prev_v : 
                prev_v = f1_v 
                create_folder('./param/lr{}_wd{}'.format(self.lr, self.wd))
                torch.save(self.model.state_dict(), './param/lr{}_wd{}/eegnet_f1_{:.2f}'.format(self.lr, self.wd, f1_v))
                self.save_checkpoint(epoch=len(self.history['train_loss']))
            
            self.write_history(self.history_mini_batch)
            # writer.add_scalar('Learning Rate', lr.get_last_lr()[-1], e)
            self.writer.add_scalar('Train/Loss', epoch_loss, e)
            self.writer.add_scalar('Train/F1', f1, e)
            self.writer.add_scalar('Train/Acc', acc, e)

            self.writer.add_scalar('Valid/Loss', loss_v, e)
            self.writer.add_scalar('Valid/F1', f1_v, e)
            self.writer.add_scalar('Valid/Acc', acc_v, e)
            self.writer.flush()

            wandb.log({"loss": epoch_loss,
                        "acc": acc,
                        "f1":f1,
                        "vloss": loss_v,
                        "vacc": acc_v,
                        "vf1":f1_v,
                        # "lr": self.optimizer.state_dict().get('param_groups')[0].get("lr")
            })
            self.scheduler.step()

        # return acc, f1, cm, epoch_loss
        return f1_v, acc_v, cm_v, loss_v

    def evaluation(self, data, interval=1000):
        data_loader = DataLoader(data, batch_size=self.args.batch_size)

        with torch.no_grad(): # gradient 안함
            self.model.eval() # dropout은 training일 때만, evaluation으로 하면 dropout 해제
            
            pred_label_acc = None
            true_label_acc = None
            pred_list = None
            true_label = None
            valid_loss = 0
            
            for idx, data in enumerate(data_loader):
                x, y = data
                true_label = y.numpy()
                b = x.shape[0]

                x = x.reshape(b, 1, self.channel_num, -1)
                pred = self.model(x.to(device=self.device).float())
                
                # 밑에 두개 중에뭐지?
                # pred = self.model(x.transpose(1,2).reshape(b,1,self.channel_num,-1).to(device=self.device).float())
                #pred = self.model(x.reshape(b,1,30,-1).to(device=device).float()) #self.model(x.transpose(1,2).reshape(b,1,30,-1).to(device=device).float())
                
                loss = self.criterion(pred, y.flatten().long().to(device=self.device)) # pred.shape
                valid_loss += loss
                # if (idx+1) % interval == 0: print('[Epoch, Step({}/{})] Valid Loss:{:.4f}'.format(idx+1, len(data)//self.args.batch_size, loss / (idx +1)))
                pred_prob = F.softmax(pred, dim=-1)
                pred_label = torch.argmax(pred_prob, dim = -1).cpu().numpy()
                # print(pred_prob)
                if pred_label_acc is None:
                    pred_label_acc = pred_label
                    true_label_acc = true_label
                else:
                    pred_label_acc = np.concatenate((pred_label_acc, pred_label), axis=None)
                    true_label_acc = np.concatenate((true_label_acc, true_label), axis=None)

                self.cal = Calculate()
                log = self.cal.calculator(metrics=self.args.metrics, loss=loss, y_true=y, y_pred=pred_label, acc_count=True)
                
                # Record history per mini-batch
                self.record_history(log, self.history_mini_batch, phase='val')
            # valid_loss = valid_loss / (idx+1)            
            # pred_list = np.concatenate(pred_list)
            # true_label = np.concatenate(true_label)
            # print(true_label_acc)
            # print(pred_label_acc)
            f1 = f1_score(true_label_acc, pred_label_acc, average='macro')
            acc = accuracy_score(true_label_acc, pred_label_acc)
            cm = confusion_matrix(true_label_acc, pred_label_acc)
            if not self.args.mode == "test":
                print('\nEpoch Validation, f1:{:.4f}, acc:{:.4f}, Loss:{:.4f}'.format(f1, acc, valid_loss))
            else:
                print('\nEpoch Test, f1:{:.4f}, acc:{:.4f}'.format(f1, acc))
            # print(cm)

        return f1, acc, cm, valid_loss


    def predict_proba(self, data, interval=1000, n_instances=1, mcdo=False, random=False, *query_args, **query_kwargs):
        data_loader = DataLoader(data, batch_size=self.args.batch_size)
        
        if not mcdo:
            with torch.no_grad(): # gradient 안함
                self.model.eval() # dropout은 training일 때만, evaluation으로 하면 dropout 해제 ############################

                pred_list = []
                uncertainty_list = []

                for idx, data in enumerate(data_loader):
                    # x = data
                    # true_label.append(y)
                    x = data
                    b = x.shape[0]

                    x = x.reshape(b, 1, self.channel_num, -1)
                    pred = self.model(x.to(device=self.device).float())

                    # pred = self.model(x.transpose(1,2).reshape(b,1,self.channel_num,-1).to(device=self.device).float())
                    pred_prob = F.softmax(pred, dim=-1)
                    # uncertainty = torch.max(pred_prob, dim=-1).values.cpu()
                    uncertainty = torch.ones(pred_prob.shape[0]).cpu() - torch.max(pred_prob, dim=-1).values.cpu()
                    pred_label = torch.argmax(pred_prob, dim = -1).cpu().numpy()
                    
                    pred_list.append(pred_label)
                    uncertainty_list.append(uncertainty)
                                
                pred_list = np.concatenate(pred_list)
                uncertainty_list = np.concatenate(uncertainty_list)
                
                if random is True:
                    print("[Random strategy]")
                    max_idx = np.random.choice(data.shape[0], 1, False)
                    
                else:
                    max_idx = multi_argmax(uncertainty_list, n_instances=n_instances)
                # print(pred_list)
                pseudo_labeling = pred_list[max_idx]
                
                # return multi_argmax(uncertainty_list, n_instances=query_kwargs['n_instances'])

        else:
            with torch.no_grad(): 
                self.model.eval()
                self.enable_dropout(self.model.clf)

                uncertainty_list = []
                mean_lists =  []

                for idx, data in enumerate(data_loader):
                    pred_list = []
                    for _ in range(10) :
                        # x = data
                        # true_label.append(y)
                        x = data
                        b = x.shape[0]

                        x = x.reshape(b, 1, self.channel_num, -1)
                        pred = self.model(x.to(device=self.device).float())
                        
                        # pred = self.model(x.transpose(1,2).reshape(b,1,self.channel_num,-1).to(device=self.device).float())
                        pred_prob = F.softmax(pred, dim=-1)
                    # uncertainty = torch.max(pred_prob, dim=-1).values.cpu()
                    
                        pred_label = torch.argmax(pred_prob, dim = -1).cpu().numpy()
                        pred_list.append(pred_label)

                    std_list = np.std(pred_list, axis=0)
                    mean_list = np.mean(pred_list, axis=0)
                    # pred_list = np.concatenate(pred_list)
                    uncertainty_list.append(std_list)
                    mean_lists.append(mean_list)
                
                uncertainty_list = np.concatenate(uncertainty_list)
                pred_list = np.concatenate(mean_lists)
                pred_list = pred_list.round(0)
                max_idx = multi_argmax(uncertainty_list, n_instances=n_instances)
                # print(pred_list)

                pseudo_labeling = pred_list[max_idx]

        return max_idx, pseudo_labeling

    def predict_score(self, data, interval=1000, *query_args, **query_kwargs):
        data_loader = DataLoader(data, batch_size=self.args.batch_size)
   
        with torch.no_grad(): # gradient 안함
            self.model.eval() # dropout은 training일 때만, evaluation으로 하면 dropout 해제 ############################
            pred_list = []
            true_label = []

            for idx, data in enumerate(data_loader):
                x, y = data
                true_label.append(y)
                b = x.shape[0]
                
                pred = self.model(x.transpose(1,2).reshape(b,1,self.channel_num,-1).to(device=self.device).float())
                pred_prob = F.softmax(pred, dim=-1)
                
                pred_label = torch.argmax(pred_prob, dim = -1).cpu().numpy()                
                pred_list.append(pred_label)

            pred_list = np.concatenate(pred_list)
            true_label = np.concatenate(true_label)
        
        f1 = f1_score(true_label, pred_list, average="macro")
        return f1

    def pseudo_label(self, data, interval=1000, *query_args, **query_kwargs):
        print("[trainer]pseudo_label에서의 print", data.x.shape)
        data_loader = DataLoader(data, batch_size=self.args.batch_size)
        pred_list = []
        with torch.no_grad(): # gradient 안함
            self.model.eval() # dropout은 training일 때만, evaluation으로 하면 dropout 해제 ############################
      
            for idx, data in enumerate(data_loader):
                x, y = data
                b = x.shape[0]
                x = x.reshape(b, 1, self.channel_num, -1)
                pred = self.model(x.to(device=self.device).float())
                # pred = self.model(x.transpose(1,2).reshape(b,1,self.channel_num,-1).to(device=self.device).float())
                pred_prob = F.softmax(pred, dim=-1)
                
                pred_label = torch.argmax(pred_prob, dim = -1).cpu().numpy() 
                pred_list.append(pred_label)
        pred_list = np.concatenate(pred_list)
        return pred_list

    def record_history(self, log, history, phase):
        for metric in log:
            history[f'{phase}_{metric}'].append(log[metric])
       
    def write_history(self, history):
        for metric in history:
            if metric.endswith('acc'):
                n_samples = self.data.x.shape[0]
                # n_samples = len(getattr(self.data, f"{metric.split('_')[0]}_loader").dataset.y)
                self.history[metric].append((sum(history[metric]) / n_samples))
            else:
                self.history[metric].append(sum(history[metric]) / len(history[metric]))
        
        # if self.args.mode == 'train':
        #     write_json(os.path.join(self.args.save_path, "history.json"), self.history)
        # else:
        #     write_json(os.path.join(self.args.save_path, "history_test.json"), self.history)

    def save_checkpoint(self, epoch):
        create_folder(os.path.join(self.args.save_path, "checkpoints"))
        torch.save({
            'epoch': epoch,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            # 'scheduler_state_dict': self.scheduler.state_dict() if self.scheduler else None
        }, os.path.join(self.args.save_path, f"checkpoints/{epoch}.tar"))
        # if epoch >= 6:
        #     os.remove(os.path.join(self.args.save_path, f"checkpoints/{epoch - 5}.tar"))
    
    def __set_criterion(self, criterion):
        if criterion == "MSE":
            criterion = nn.MSELoss()
        elif criterion == "CEE":
            criterion = nn.CrossEntropyLoss()
        elif criterion == "Focal":
            criterion = FocalLoss(gamma=2)
        elif criterion == "ND":
            criterion = CrossentropyND()
        elif criterion == "TopK":
            criterion = TopKLoss()
        elif criterion == "LS":
            criterion = LabelSmoothingCrossEntropy()
        return criterion
    
    def __set_scheduler(self, args, optimizer):
        if args.scheduler is None:
            return None
        elif args.scheduler == 'exp':
            scheduler = optim.lr_scheduler.ExponentialLR(optimizer, gamma=args.gamma)
        elif args.scheduler == 'step':
            scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=args.step_size, gamma=args.gamma)
        elif args.scheduler == 'multi_step':
            scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones=args.milestones, gamma=args.gamma)
        elif args.scheduler == 'plateau':
            scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.1, patience=20,
                                                             threshold=0.1, threshold_mode='abs', verbose=True)
        elif args.scheduler == 'cosine':
            scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer,
                                                             T_max=args.T_max if args.T_max else args.epochs,
                                                             eta_min=args.eta_min if args.eta_min else 0)
        else:
            raise ValueError(f"Not supported {args.scheduler}.")
        return scheduler

    def enable_dropout(self, model):
        """ Function to enable the dropout layers during test-time """
        for m in model.modules():
            if m.__class__.__name__.startswith('Dropout'):
                m.train()


    # def __make_trainer(self, **kwself.args):
    #     module = importlib.import_module(f"trainers.{kwself.args['self.args'].model}_trainer")
    #     trainer = getattr(module, 'Trainer')(**kwargs)
    #     return trainer

class Calculate:
    def calculator(self, metrics, loss, y_true, y_pred, numpy=True, **kwargs):
        if numpy:
            y_true = self.guarantee_numpy(y_true)
            y_pred = self.guarantee_numpy(y_pred)

        history = defaultdict(list)
        for metric in metrics:
            history[metric] = getattr(self, f"get_{metric}")(loss=loss, y_true=y_true, y_pred=y_pred, **kwargs)
        return history

    def get_loss(self, loss, **kwargs):
            return float(loss)

    def get_acc(self, y_true, y_pred, acc_count=False, **kwargs):
        if acc_count:
            return sum(y_true == y_pred)
        else:
            return sum(y_true == y_pred) / len(y_true)

    def guarantee_numpy(self, data):
        data_type = type(data)
        if data_type == torch.Tensor:
            device = data.device.type
            if device == 'cpu':
                data = data.detach().numpy()
            else:
                data = data.detach().cpu().numpy()
            return data
        elif data_type == np.ndarray or data_type == list:
            return data
        else:
            raise ValueError("Check your data type.")
=======
from numpy.lib.function_base import average
from sklearn.utils import shuffle
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils import data
from torch.utils.data import DataLoader
from sklearn.metrics import f1_score, accuracy_score, confusion_matrix
import numpy as np
import pandas as pd
from tqdm import tqdm
from torch.utils.tensorboard import SummaryWriter
import os
from utils import *
from loss.ND_Crossentropy import CrossentropyND, TopKLoss
from loss.focalloss import *
from loss.label_smoothing import LabelSmoothingCrossEntropy
from MS_code.utils import gpu_checking
import importlib

class TrainMaker:
    def __init__(self, args, model, data):
            self.writer = SummaryWriter(log_dir='./runs/lr{}_wd{}'.format(args.lr, args.wd))
            ##tensorboard --logdir=C:/Users/soso/Desktop/tensorboard/runs --port 6006
            optimizer = getattr(torch.optim, args.optimizer)
            criterion = getattr(torch.nn, self.__set_criterion(args.criterion))
            self.model = model
            self.optimizer = optimizer(model.parameters(), lr=args.lr, weight_decay=args.wd)
            self.epoch = args.epoch
            # self.criterion = args.__set_criterion(args.criterion)
            self.criterion = criterion
            self.lr = args.lr
            self.wd = args.wd
            self.channel_num = args.channel_num
            self.data = data
            self.device = gpu_checking()
            if args.mode == "train":
                self.trainer = self.__make_trainer(args=args,
                                                    model=self.model,
                                                    data=data,
                                                    criterion=self.criterion,
                                                    optimizer=self.optimizer)
            

    def train(self, args, shuffle=True, interval=1000):
        # train_data, valid_data = torch.utils.data.random_split(data, [int(len(data) * 0.8), (len(data) - int(len(data) * 0.8))]) # data.split(split_ratio = 0.8)
        train_data = self.data
        
        prev_v = -10
        data_loader = DataLoader(train_data, batch_size=args.batch_size, shuffle = shuffle)

        for e in tqdm(range(self.epoch)):
            epoch_loss = 0
            self.model.train() # train 시키기
            pred_list = []
            true_label = []
            for idx, data in enumerate(data_loader): # enumerate -> batch size 정한만큼 꺼내오기.
                x, y = data # 튜플에서 x, y 하나씩 넣기
                true_label.append(y)
                b = x.shape[0] # 30 --> 1?
                
                self.optimizer.zero_grad() # optimizer 항상 초기화 
                #x = x.reshape(b,1,30,-1) ############## checking [1, 1, 30, 700] 미츼ㅣㅣ
                x = x.reshape(b, 1, self.channel_num, -1) # [1, 1, 25, 750]
                pred = self.model(x.to(device=self.device).float())

                # pred, (hidden_state, cell_state) = network(x.view(b, 1, -1).float().to(device=device), (hidden_state[:,:b].detach().contiguous(), cell_state[:,:b].detach().contiguous())) # view함수 -> 밑에 적음
                loss = self.criterion(pred, y.flatten().long().to(device=self.device)) 
                if (idx+1) % interval == 0: print('[Epoch{}, Step({}/{})] Loss:{:.4f}'.format(e+1, idx+1, len(data_loader.dataset)//batch_size, epoch_loss / (idx +1)))

                loss.backward()
                epoch_loss += loss.item()
                self.optimizer.step()
                pred_prob = F.softmax(pred, dim=-1)
                pred_label = torch.argmax(pred_prob, dim=-1).cpu().numpy()
                pred_list.append(pred_label) # pred_list에 prediction 넣어주기

            pred_list = np.concatenate(pred_list)
            true_label = np.concatenate(true_label)
            
            # print("true_label:", true_label)
            # print(true_label)
            # print("\n\n\n", pred_list)
            f1 = f1_score(true_label, pred_list, average='macro') 
            acc = accuracy_score(true_label, pred_list)
            cm = confusion_matrix(true_label, pred_list)
            epoch_loss = epoch_loss / (idx+1)

            print('\nEpoch{} Training, f1:{:.4f}, acc:{:.4f}, Loss:{:.4f}'.format(e+1, f1, acc, epoch_loss))
            print(cm)

            f1_v, acc_v, cm_v, loss_v = self.prediction(valid_data, batch_size)
            if f1_v > prev_v : 
                prev_v = f1_v
                if not os.path.exists('./param/lr{}_wd{}'.format(self.lr, self.wd)): ################################################ 위치
                    os.mkdir('./param/lr{}_wd{}'.format(self.lr, self.wd))
                torch.save(self.model.state_dict(), './param/lr{}_wd{}/eegnet_f1_{:.2f}'.format(self.lr, self.wd, f1_v))
                # torch.save(self.model.state_dict(), '/opt/workspace/soxo/code_ms/param/lr{}_wd{}/eegnet_f1_{:.2f}'.format(self.lr, self.wd, f1_v))

            # writer.add_scalar('Learning Rate', lr.get_last_lr()[-1], e)
            self.writer.add_scalar('Train/Loss', epoch_loss, e)
            self.writer.add_scalar('Train/F1', f1, e)
            self.writer.add_scalar('Train/Acc', acc, e)

            self.writer.add_scalar('Valid/Loss', loss_v, e)
            self.writer.add_scalar('Valid/F1', f1_v, e)
            self.writer.add_scalar('Valid/Acc', acc_v, e)
            self.writer.flush()
        return acc, f1, cm, epoch_loss


    def evaluation(self, batch_size, interval=1000):
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        data_loader = DataLoader(self.data, batch_size = batch_size)

        with torch.no_grad(): # gradient 안함
            self.model.eval() # dropout은 training일 때만, evaluation으로 하면 dropout 해제
            pred_list = []
            true_label = []
            valid_loss = 0
            
            for idx, data in enumerate(data_loader):
                x, y = data
                true_label.append(y)
                b = x.shape[0]

                # 밑에 두개 중에뭐지?
                pred = self.model(x.transpose(1,2).reshape(b,1,self.channel_num,-1).to(device=self.device).float())
                #pred = self.model(x.reshape(b,1,30,-1).to(device=device).float()) #self.model(x.transpose(1,2).reshape(b,1,30,-1).to(device=device).float())
                loss = self.criterion(pred, y.flatten().long().to(device=self.device)) # pred.shape
                valid_loss += loss
                if (idx+1) % interval == 0: print('[Epoch, Step({}/{})] Valid Loss:{:.4f}'.format(idx+1, len(data)//batch_size, loss / (idx +1)))
                pred_prob = F.softmax(pred, dim=-1)
                pred_label = torch.argmax(pred_prob, dim = -1).cpu().numpy()
                pred_list.append(pred_label)

            valid_loss = valid_loss / (idx+1)            
            pred_list = np.concatenate(pred_list)
            true_label = np.concatenate(true_label)
            
            f1 = f1_score(true_label, pred_list, average='macro')
            acc = accuracy_score(true_label, pred_list)
            cm = confusion_matrix(true_label, pred_list)
            if not test:
                print('\nEpoch Validation, f1:{:.4f}, acc:{:.4f}, Loss:{:.4f}'.format(f1, acc, valid_loss))
            else:
                print('\nEpoch Test, f1:{:.4f}, acc:{:.4f}'.format(f1, acc))
            print(cm)

        return f1, acc, cm, valid_loss

    
     
    def __set_criterion(self, criterion):
        if criterion == "MSE":
            criterion = nn.MSELoss()
        elif criterion == "CEE":
            criterion = nn.CrossEntropyLoss()
        elif criterion == "Focal":
            criterion = FocalLoss(gamma=2)
        elif criterion == "ND":
            criterion = CrossentropyND()
        elif criterion == "TopK":
            criterion = TopKLoss()
        elif criterion == "LS":
            criterion = LabelSmoothingCrossEntropy()
        return criterion

    def __make_trainer(self, **kwargs):
        module = importlib.import_module(f"trainers.{kwargs['args'].model}_trainer")
        trainer = getattr(module, 'Trainer')(**kwargs)
        return trainer
>>>>>>> 72fde0adfb169b7aca75faba81f54913d760ae5c
