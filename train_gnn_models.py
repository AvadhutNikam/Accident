import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import LabelEncoder
import math
import argparse
import os
import pickle
from collections import defaultdict
import datetime

# ---------------------------------------------------------------------------
# STGCN PyTorch Native Implementation
# ---------------------------------------------------------------------------
class GraphConvolution(nn.Module):
    def __init__(self, in_features, out_features):
        super(GraphConvolution, self).__init__()
        self.weight = nn.Parameter(torch.FloatTensor(in_features, out_features))
        self.bias = nn.Parameter(torch.FloatTensor(out_features))
        nn.init.xavier_uniform_(self.weight)
        nn.init.zeros_(self.bias)

    def forward(self, text, adj):
        support = torch.matmul(text, self.weight)
        output = torch.matmul(adj, support)
        return output + self.bias

class STGCNClassifier(nn.Module):
    """
    Spatial-Temporal Graph Convolutional Network (STGCN)
    Analyzes physical road topology mapping overlapping weather/temporal states
    """
    def __init__(self, nfeat, nhid, nclass, dropout=0.3):
        super(STGCNClassifier, self).__init__()
        self.gc1 = GraphConvolution(nfeat, nhid)
        self.gc2 = GraphConvolution(nhid, nhid)
        self.fc = nn.Linear(nhid, nclass)
        self.dropout = nn.Dropout(dropout)
        self.activation = nn.ReLU()

    def forward(self, x, adj):
        x = self.activation(self.gc1(x, adj))
        x = self.dropout(x)
        x = self.activation(self.gc2(x, adj))
        return self.fc(x)

# ---------------------------------------------------------------------------
# Data Math & Preprocessing
# ---------------------------------------------------------------------------
WEATHER_RISK_SCORE = {"Clear": 0, "Rain": 4, "Fog": 5, "Heavy Rain": 8}
WEATHER_RAIN_MM = {"Clear": 0.0, "Rain": 3.5, "Fog": 0.2, "Heavy Rain": 12.0}
WEATHER_HUMIDITY = {"Clear": 55, "Rain": 82, "Fog": 90, "Heavy Rain": 88}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def build_adjacency_matrix(segments_df, threshold_km=0.5):
    """
    Mathematically constructs graph topology of the city.
    Nodes are road segments. Edges are intersections within threshold distance.
    """
    n = len(segments_df)
    A = np.zeros((n, n), dtype=np.float32)
    coords = segments_df[['start_lat', 'start_lon', 'end_lat', 'end_lon']].values
    
    # Very rudimentary O(N^2) overlap detection for presentation demo
    for i in range(n):
        slat1, slon1, elat1, elon1 = coords[i]
        for j in range(i+1, n):
            slat2, slon2, elat2, elon2 = coords[j]
            # If endpoints intersect within 500 meters, establish graph edge
            if min([
                haversine(slat1, slon1, slat2, slon2),
                haversine(slat1, slon1, elat2, elon2),
                haversine(elat1, elon1, slat2, slon2),
                haversine(elat1, elon1, elat2, elon2)
            ]) < threshold_km:
                A[i, j] = 1.0
                A[j, i] = 1.0
                
    # Normalize Graph Laplacian D^-1/2 * A * D^-1/2 logically
    A = A + np.eye(n) # Self loops
    D_inv_sqrt = np.power(np.sum(A, axis=1), -0.5)
    D_inv_sqrt[np.isinf(D_inv_sqrt)] = 0.
    D_mat_inv_sqrt = np.diag(D_inv_sqrt)
    A_norm = D_mat_inv_sqrt.dot(A).dot(D_mat_inv_sqrt)
    
    return torch.FloatTensor(A_norm)

def train_city_gnn(city_id):
    print(f"\n============================================================")
    print(f"Training STGCN PyTorch Topology for: {city_id.upper()}")
    print(f"============================================================")
    
    data_dir = f"data/{city_id}"
    model_dir = f"models/{city_id}"
    os.makedirs(model_dir, exist_ok=True)
    
    acc_df = pd.read_csv(f"{data_dir}/accidents.csv")
    seg_df = pd.read_csv(f"{data_dir}/road_segments.csv")
    
    if len(seg_df) == 0:
        print("No road data found.")
        return
        
    # Build Adjacency Graph natively
    print("[GNN] Computing spatial Adjacency Matrix...")
    adj = build_adjacency_matrix(seg_df)
    
    # Feature extraction per node
    # Since nodes are segments, aggregate accidents historically per segment
    print("[GNN] Aggregating Node Features...")
    risk_map = {"low": 0, "medium": 1, "high": 2}
    
    # N-dimensional node features
    X = np.zeros((len(seg_df), 4), dtype=np.float32)
    Y = np.zeros(len(seg_df), dtype=np.int64)
    
    for i, (idx, row) in enumerate(seg_df.iterrows()):
        base = risk_map.get(row['risk_level'], 1)
        traffic = min(row['avg_traffic']/20000.0, 1.0)
        
        # Determine accidents on this node historically
        # Roughly aggregate bounding box
        node_accs = acc_df[(acc_df['latitude'] >= row['start_lat'] - 0.05) & 
                           (acc_df['latitude'] <= row['start_lat'] + 0.05)]
        
        fatal_count = len(node_accs[node_accs['severity'].str.lower() == 'fatal'])
        sev_count = len(node_accs[node_accs['severity'].str.lower() == 'severe'])
        
        hist_risk = fatal_count * 3 + sev_count * 1
        X[i] = [base, traffic, len(node_accs), hist_risk]
        
        if hist_risk > 3: Y[i] = 2 # High
        elif hist_risk > 0: Y[i] = 1 # Med
        else: Y[i] = 0 # Low

    X_tensor = torch.FloatTensor(X)
    Y_tensor = torch.LongTensor(Y)
    
    model = STGCNClassifier(nfeat=X.shape[1], nhid=16, nclass=3)
    optimizer = optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)
    criterion = nn.CrossEntropyLoss()
    
    print("[GNN] Training PyTorch Graphical Network...")
    for epoch in range(100):
        model.train()
        optimizer.zero_grad()
        output = model(X_tensor, adj)
        loss = criterion(output, Y_tensor)
        loss.backward()
        optimizer.step()
        
        if epoch % 20 == 0:
            pred = output.argmax(dim=1)
            acc = (pred == Y_tensor).float().mean()
            print(f"  Epoch {epoch:03d}: Loss={loss.item():.4f}, Graph Spatial Accuracy={acc.item():.4f}")
            
    print("[GNN] Compiling final STGCN inference state...")
    model.eval()
    with torch.no_grad():
        final_out = model(X_tensor, adj)
        final_probs = torch.softmax(final_out, dim=1)
        
    torch.save({
        'model_state': model.state_dict(),
        'adj_matrix': adj,
        'base_X': X_tensor
    }, f"{model_dir}/stgcn_model.pth")
    
    print(f"[GNN] Successfully cached trained graph network to {model_dir}/stgcn_model.pth\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--city', type=str)
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    
    cities = ['mumbai', 'pune', 'delhi', 'bangalore', 'chennai', 'kolkata', 'hyderabad', 'chandigarh']
    cities_to_train = [args.city] if args.city else (cities if args.all else [])
    
    for city in cities_to_train:
        train_city_gnn(city)
