// Exact, cost-unique three-objective shortest paths. No approximate pruning.
// Build: g++ -O3 -DNDEBUG -std=c++17 task2_exact.cpp -o task2_exact.exe -lpsapi -lshell32
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <queue>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#include <shellapi.h>
#else
#include <sys/resource.h>
#endif

using U = uint64_t;
using Node = uint32_t;
using Cost = std::array<U, 3>;
using Clock = std::chrono::steady_clock;
namespace fs = std::filesystem;
constexpr U INF = std::numeric_limits<U>::max() / 4;
constexpr const char* VERSION = "TASK2_EXACT_V1";
static std::array<int,3> objective_order{0,1,2};
static std::string order_text="123";
static Cost internal(Cost c) {return {c[objective_order[0]],c[objective_order[1]],c[objective_order[2]]};}
static Cost original(Cost c) {
    Cost z{};for(int j=0;j<3;++j) z[objective_order[j]]=c[j];return z;
}
static bool leq(const Cost& a, const Cost& b) {
    return a[0] <= b[0] && a[1] <= b[1] && a[2] <= b[2];
}
static Cost plus(const Cost& a, const Cost& b) {
    Cost c{};
    for (int j=0;j<3;++j) c[j] = a[j]>=INF-b[j] ? INF : a[j]+b[j];
    return c;
}
static double seconds(Clock::time_point t) {
    return std::chrono::duration<double>(Clock::now()-t).count();
}
static U peak_rss_mb() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS p{};
    if (GetProcessMemoryInfo(GetCurrentProcess(), &p, sizeof(p)))
        return p.PeakWorkingSetSize / (1024*1024);
#else
    struct rusage usage{};
    if(getrusage(RUSAGE_SELF,&usage)==0) return static_cast<U>(usage.ru_maxrss)/1024;
#endif
    return 0;
}
static U number(const std::string& s) {
    if (s.empty() || s.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("expected unsigned integer: " + s);
    size_t used=0; U v=std::stoull(s,&used);
    if (used!=s.size()) throw std::runtime_error("invalid integer: " + s);
    return v;
}
static Node node_number(const std::string& s) {
    U v=number(s);
    if (v>=UINT32_MAX) throw std::runtime_error("node ID too large");
    return static_cast<Node>(v);
}
struct Raw { Node u,v; Cost c; };
struct Edge { Node to; Cost c; };
struct Graph {
    Node n=0;
    std::vector<Node> off, roff;
    std::vector<Edge> edges, reverse;
    Graph() = default;
    Graph(Node nn, const std::vector<Raw>& raw): n(nn),off(n+1),roff(n+1) {
        if (raw.size()>=UINT32_MAX) throw std::runtime_error("too many edges");
        Cost mx{};
        for (const auto& e:raw) {
            if(e.u>=n || e.v>=n) throw std::runtime_error("edge outside graph");
            ++off[e.u+1]; ++roff[e.v+1];
            for(int j=0;j<3;++j) mx[j]=std::max(mx[j],e.c[j]);
        }
        // Every retained label has a cycle-free representative. Leave room
        // for a prefix, one edge, and a heuristic suffix, without saturation.
        for(U x:mx) if(static_cast<__int128>(x)*(2ULL*n+1)>=INF)
            throw std::runtime_error("cost range exceeds exact integer capacity");
        for(Node v=1;v<=n;++v) {off[v]+=off[v-1]; roff[v]+=roff[v-1];}
        edges.resize(raw.size()); reverse.resize(raw.size());
        auto a=off,b=roff;
        for(const auto& e:raw) {
            edges[a[e.u]++]={e.v,e.c}; reverse[b[e.v]++]={e.u,e.c};
        }
    }
    static Graph load(const fs::path& path) {
        std::ifstream in(path);
        if(!in) throw std::runtime_error("cannot read graph: "+path.string());
        std::vector<Raw> raw;
        std::string line; Node n=0;
        while(std::getline(in,line)) {
            auto start=line.find_first_not_of(" \t\r");
            if(start==std::string::npos || line[start]=='#') continue;
            std::istringstream row(line); std::array<std::string,7> x; std::string extra;
            for(auto& s:x) if(!(row>>s)) throw std::runtime_error("truncated edge row");
            if(row>>extra) throw std::runtime_error("extra edge field");
            Node u=node_number(x[0]),v=node_number(x[1]);
            Cost c{number(x[2]),number(x[3]),number(x[4])};
            number(x[5]);number(x[6]);
            raw.push_back({u,v,internal(c)}); n=std::max(n,std::max(u,v)+1);
        }
        if(!in.eof()) throw std::runtime_error("graph read failed");
        if(!n) throw std::runtime_error("empty graph");
        return Graph(n,raw);
    }
};

// Ordered 2D skyline. Keys increase, values strictly decrease.
// Valid as a 3D filter ONLY when the omitted first coordinate is no larger
// for every previously inserted label (proved by lexicographic f ordering).
struct Skyline2 {
    // The user's task2_fast_exact.cpp uses sorted contiguous 2D frontiers.
    // This avoids a tree allocation per point; insertion is O(frontier size).
    std::vector<std::pair<U,U>> points;
    bool dominates(U a,U b) const {
        auto it=std::upper_bound(points.begin(),points.end(),a,[](U x,const auto& p){return x<p.first;});
        return it!=points.begin() && std::prev(it)->second<=b;
    }
    bool insert(U a,U b) {
        if(dominates(a,b)) return false;
        auto it=std::lower_bound(points.begin(),points.end(),a,[](const auto& p,U x){return p.first<x;});
        auto end=it;while(end!=points.end() && end->second>=b) ++end;
        it=points.erase(it,end);points.insert(it,{a,b});return true;
    }
};
static std::vector<Cost> frontier(std::vector<Cost> x) {
    std::sort(x.begin(),x.end());
    Skyline2 f; std::vector<Cost> out;
    for(auto c:x) if(f.insert(c[1],c[2])) out.push_back(c);
    return out;
}

struct Heuristic {
    std::array<std::vector<U>,3> d;
    std::array<std::vector<Node>,3> next_node,next_edge;
    auto& operator[](int j) {return d[j];}
    const auto& operator[](int j) const {return d[j];}
};
static Heuristic lower_bounds(const Graph& g,Node target) {
    Heuristic h;
    for(int j=0;j<3;++j) {
        auto& d=h[j];d.assign(g.n,INF);d[target]=0;
        h.next_node[j].assign(g.n,UINT32_MAX);h.next_edge[j].assign(g.n,UINT32_MAX);
        using Item=std::pair<U,Node>;
        std::priority_queue<Item,std::vector<Item>,std::greater<Item>> q;
        q.push({0,target});
        while(!q.empty()) {
            auto [du,u]=q.top();q.pop();if(du!=d[u]) continue;
            for(Node k=g.roff[u];k<g.roff[u+1];++k) {
                const auto& e=g.reverse[k]; U nd=du+e.c[j];
                if(nd<d[e.to]) {
                    d[e.to]=nd;h.next_node[j][e.to]=u;h.next_edge[j][e.to]=k;q.push({nd,e.to});
                }
            }
        }
    }
    return h;
}

// Feasible seeds are ONLY full-3D upper bounds. Weighted sums never replace
// enumeration. Keep the actual predecessor edge, including parallel edges.
static Cost seed_path(const Graph& g,Node s,Node t,const Cost& w) {
    using Wide=__int128;
    using Item=std::pair<Wide,Node>;
    std::vector<Wide> d(g.n,-1);
    std::vector<Node> parent(g.n,UINT32_MAX),edge_id(g.n,UINT32_MAX);
    std::priority_queue<Item,std::vector<Item>,std::greater<Item>> q;
    d[s]=0;q.push({0,s});
    while(!q.empty()) {
        auto [du,u]=q.top();q.pop();if(du!=d[u]) continue;if(u==t) break;
        for(Node k=g.off[u];k<g.off[u+1];++k) {
            const auto& e=g.edges[k];Wide nd=du;
            for(int j=0;j<3;++j) nd+=static_cast<Wide>(e.c[j])*w[j];
            if(d[e.to]<0 || nd<d[e.to]) {
                d[e.to]=nd;parent[e.to]=u;edge_id[e.to]=k;q.push({nd,e.to});
            }
        }
    }
    if(d[t]<0) return {INF,INF,INF};
    Cost total{};
    for(Node v=t;v!=s;v=parent[v]) total=plus(total,g.edges[edge_id[v]].c);
    return total;
}
struct Limits { double max_seconds=0; U max_expanded=0,max_open=0; int seeds=3; bool quiet=false; };
struct Metrics {
    U expanded=0,generated=0,pushed=0,popped=0,peak_open=0,skyline_points=0;
    double elapsed=0; U rss=0;
};
struct Result { bool complete=false;std::string reason;std::vector<Cost> costs;Metrics m; };
static Result solve(const Graph& g,Node s,Node t,const Heuristic& h,const Limits& lim) {
    auto start=Clock::now(),last=start;
    Result r;
    auto finish=[&](bool complete,const std::string& reason) {
        r.complete=complete;r.reason=reason;r.m.elapsed=seconds(start);r.m.rss=peak_rss_mb();
        if(complete) r.costs=frontier(std::move(r.costs));
        else r.costs.clear(); // partial incumbent sets are not exact results
        return r;
    };
    if(h[0][s]==INF) return finish(true,"unreachable");
    if(s==t) {r.costs.push_back({0,0,0});return finish(true,"complete");}
    std::vector<Cost> seeds;
    // Reuse the actual reverse-Dijkstra edges for every query sharing t.
    // In particular, do not recover a parallel edge by node endpoints alone.
    for(int j=0;j<3;++j) {
        Cost c{};for(Node v=s;v!=t;v=h.next_node[j][v]) c=plus(c,g.reverse[h.next_edge[j][v]].c);
        seeds.push_back(c);
    }
    const std::array<Cost,7> prefs{{{1,1,1},{4,1,1},{1,4,1},{1,1,4},{4,4,1},{4,1,4},{1,4,4}}};
    for(int k=0;k<lim.seeds-3;++k) {
        Cost w{};
        for(int j=0;j<3;++j) w[j]=std::max<U>(1,1000000/std::max<U>(1,h[j][s]))*prefs[k][j];
        seeds.push_back(seed_path(g,s,t,w));
    }
    seeds=frontier(std::move(seeds));r.costs=seeds;
    auto seeded=[&](const Cost& f) {for(const auto& x:seeds) if(leq(x,f)) return true;return false;};
    struct Item { Cost f;Node v; };
    struct Greater {
        bool operator()(const Item& a,const Item& b) const {
            return a.f!=b.f ? a.f>b.f : a.v>b.v;
        }
    };
    std::priority_queue<Item,std::vector<Item>,Greater> open;
    std::vector<Skyline2> local(g.n);Skyline2 goals;
    open.push({{h[0][s],h[1][s],h[2][s]},s});r.m.pushed=1;r.m.peak_open=1;
    while(!open.empty()) {
        if(lim.max_seconds>0 && seconds(start)>=lim.max_seconds) return finish(false,"time_limit");
        const auto x=open.top();open.pop();++r.m.popped;
        const auto& f=x.f; Node u=x.v;
        Cost cost{f[0]-h[0][u],f[1]-h[1][u],f[2]-h[2][u]};
        if(goals.dominates(f[1],f[2]) || seeded(f) || local[u].dominates(cost[1],cost[2])) continue;
        if(u==t) {
            goals.insert(cost[1],cost[2]);r.costs.push_back(cost);continue;
        }
        if(lim.max_expanded && r.m.expanded>=lim.max_expanded) return finish(false,"expansion_limit");
        auto old=local[u].points.size();local[u].insert(cost[1],cost[2]);
        r.m.skyline_points=r.m.skyline_points-old+local[u].points.size();++r.m.expanded;
        for(Node k=g.off[u];k<g.off[u+1];++k) {
            const auto& e=g.edges[k];Node v=e.to;++r.m.generated;
            if(h[0][v]==INF) continue;
            Cost ng=plus(cost,e.c),nf=plus(ng,{h[0][v],h[1][v],h[2][v]});
            // All h_j are consistent; every generated f_j >= its parent's f_j.
            // Thus the projected filters are safe both here and on popping.
            if(goals.dominates(nf[1],nf[2]) || local[v].dominates(ng[1],ng[2]) || seeded(nf)) continue;
            if(lim.max_open && open.size()>=lim.max_open) return finish(false,"open_limit");
            open.push({nf,v});++r.m.pushed;r.m.peak_open=std::max<U>(r.m.peak_open,open.size());
        }
        if(!lim.quiet && seconds(last)>=5) {
            last=Clock::now();
            std::cerr<<"  search_s="<<seconds(start)<<" expanded="<<r.m.expanded
                     <<" open="<<open.size()<<" local_skyline="<<r.m.skyline_points
                     <<" solutions_found="<<r.costs.size()<<" process_peak_MB="<<peak_rss_mb()<<'\n';
        }
    }
    return finish(true,"complete");
}

struct Query {std::string dataset,id;Node s,t;std::string fingerprint;};
static bool safe_id(const std::string& s) {
    return !s.empty() && s.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")==std::string::npos;
}
static std::vector<Query> read_queries(const fs::path& path,const std::string& ds) {
    std::ifstream in(path);if(!in) throw std::runtime_error("cannot read queries: "+path.string());
    std::string line;std::getline(in,line);
    if(!line.empty() && line.back()=='\r') line.pop_back();
    if(line!="query_id,source,target") throw std::runtime_error("unexpected query header");
    std::vector<Query> out;std::set<std::string> ids;
    while(std::getline(in,line)) {
        if(!line.empty() && line.back()=='\r') line.pop_back();
        if(line.empty()) continue;
        std::istringstream row(line);std::string id,s,t,extra;
        if(!std::getline(row,id,',') || !std::getline(row,s,',') || !std::getline(row,t,',') || std::getline(row,extra,','))
            throw std::runtime_error("invalid query row");
        if(!safe_id(id) || !ids.insert(id).second) throw std::runtime_error("invalid/duplicate query ID");
        out.push_back({ds,id,node_number(s),node_number(t),""});
    }
    return out;
}
static std::string fingerprint(const fs::path& a,const fs::path& b) {
    U h=14695981039346656037ULL;
    for(const auto& p:{a,b}) {
        std::ifstream in(p,std::ios::binary);if(!in) throw std::runtime_error("cannot fingerprint input");
        char buf[65536];
        while(in.read(buf,sizeof(buf)) || in.gcount()) for(std::streamsize i=0;i<in.gcount();++i) {
            h^=static_cast<unsigned char>(buf[i]);h*=1099511628211ULL;
        }
        if(!in.eof()) throw std::runtime_error("input read failed");
        h^=255;h*=1099511628211ULL;
    }
    std::ostringstream out;out<<std::hex<<h;return out.str();
}
static void atomic_write(const fs::path& path,const std::string& contents) {
    auto tmp=path;tmp+=".tmp";
    {std::ofstream out(tmp,std::ios::binary|std::ios::trunc);out<<contents;out.flush();
     if(!out) throw std::runtime_error("output write failed: "+tmp.string());}
#ifdef _WIN32
    if(!MoveFileExW(tmp.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))
        throw std::runtime_error("atomic output replacement failed");
#else
    fs::rename(tmp,path);
#endif
}
static fs::path checkpoint(const fs::path& dir,const Query& q) {return dir/(q.dataset+"_"+q.id+".exact");}
static void save(const fs::path& dir,const Query& q,const Result& r) {
    if(!r.complete) throw std::runtime_error("refusing to checkpoint partial frontier");
    std::ostringstream out;
    out<<VERSION<<' '<<q.dataset<<' '<<q.id<<' '<<q.s<<' '<<q.t<<' '<<q.fingerprint<<' '<<r.costs.size()<<'\n';
    const auto& m=r.m;
    out<<m.expanded<<' '<<m.generated<<' '<<m.pushed<<' '<<m.popped<<' '<<m.peak_open<<' '
       <<m.skyline_points<<' '<<std::setprecision(12)<<m.elapsed<<' '<<m.rss<<'\n';
    for(auto c:r.costs) out<<c[0]<<' '<<c[1]<<' '<<c[2]<<'\n';
    atomic_write(checkpoint(dir,q),out.str());
}
static Result restore(const fs::path& dir,const Query& q) {
    std::ifstream in(checkpoint(dir,q));if(!in) throw std::runtime_error("cannot read checkpoint");
    std::string version,ds,id,hash;Node s,t;U n;
    if(!(in>>version>>ds>>id>>s>>t>>hash>>n) || version!=VERSION || ds!=q.dataset || id!=q.id || s!=q.s || t!=q.t || hash!=q.fingerprint)
        throw std::runtime_error("checkpoint/input mismatch: "+q.dataset+"/"+q.id);
    Result r;r.complete=true;r.reason=n?"complete":"unreachable";auto& m=r.m;
    if(!(in>>m.expanded>>m.generated>>m.pushed>>m.popped>>m.peak_open>>m.skyline_points>>m.elapsed>>m.rss))
        throw std::runtime_error("truncated checkpoint metrics");
    for(U i=0;i<n;++i) {
        Cost c;if(!(in>>c[0]>>c[1]>>c[2]) || *std::max_element(c.begin(),c.end())>=INF)
            throw std::runtime_error("truncated/invalid checkpoint frontier");
        r.costs.push_back(c);
    }
    std::string extra;if(in>>extra) throw std::runtime_error("extra checkpoint data");
    if(frontier(r.costs)!=r.costs) throw std::runtime_error("checkpoint frontier is not canonical");
    return r;
}
static void export_results(const fs::path& dir,const fs::path& csv,const std::vector<Query>& all,
                           const std::map<std::string,Result>& attempted) {
    std::ostringstream out,status;
    bool all_complete=true;
    out<<"dataset,query_id,source,target,solution_id,c1,c2,c3\n";
    status<<"dataset,query_id,source,target,status,solutions,search_seconds,expanded,generated,peak_open,process_peak_rss_mb\n";
    for(const auto& q:all) {
        Result r;
        if(fs::exists(checkpoint(dir,q))) r=restore(dir,q);
        else {
            auto it=attempted.find(q.dataset+"/"+q.id);
            if(it!=attempted.end()) r=it->second;else r.reason="not_run";
        }
        if(!r.complete) all_complete=false;
        if(r.complete) for(size_t i=0;i<r.costs.size();++i) {
            auto c=r.costs[i];out<<q.dataset<<','<<q.id<<','<<q.s<<','<<q.t<<','<<i+1<<','<<c[0]<<','<<c[1]<<','<<c[2]<<'\n';
        }
        status<<q.dataset<<','<<q.id<<','<<q.s<<','<<q.t<<','<<r.reason<<','<<r.costs.size()<<','
              <<r.m.elapsed<<','<<r.m.expanded<<','<<r.m.generated<<','<<r.m.peak_open<<','<<r.m.rss<<'\n';
    }
    auto destination=csv;
    if(!all_complete) {auto name=csv.filename();name.replace_extension(".partial.csv");destination=csv.parent_path()/name;}
    atomic_write(destination,out.str());atomic_write(csv.parent_path()/"task2_status.csv",status.str());
}

// Independent reference: enumerate all simple paths, then pairwise dominance.
static std::vector<Cost> brute(const Graph& g,Node s,Node t) {
    std::vector<Cost> paths;std::vector<bool> seen(g.n,false);
    auto dfs=[&](auto&& self,Node u,Cost c)->void {
        if(u==t) {paths.push_back(c);return;} seen[u]=true;
        for(Node k=g.off[u];k<g.off[u+1];++k) if(!seen[g.edges[k].to]) self(self,g.edges[k].to,plus(c,g.edges[k].c));
        seen[u]=false;
    };
    dfs(dfs,s,{0,0,0});std::sort(paths.begin(),paths.end());paths.erase(std::unique(paths.begin(),paths.end()),paths.end());
    std::vector<Cost> out;
    for(auto c:paths) {bool dominated=false;for(auto d:paths) if(c!=d && leq(d,c)) {dominated=true;break;}if(!dominated) out.push_back(c);}
    return out;
}
static int self_test() {
    std::mt19937 rng(20260831);Limits lim;lim.quiet=true;
    for(int tc=0;tc<2000;++tc) {
        Node n=2+rng()%7;std::vector<Raw> edges;
        for(Node u=0;u<n;++u) for(Node v=0;v<n;++v) if(rng()%100<23) {
            edges.push_back({u,v,{rng()%9,rng()%9,rng()%9}});
            if(rng()%5==0) edges.push_back({u,v,{rng()%9,rng()%9,rng()%9}});
            if(rng()%11==0) edges.push_back({u,v,{0,0,0}});
        }
        Graph g(n,edges);Node s=rng()%n,t=rng()%n;auto expected=brute(g,s,t);
        objective_order={0,1,2};
        do {
            auto permuted=edges;for(auto& e:permuted) e.c=internal(e.c);
            Graph p(n,permuted);auto h=lower_bounds(p,t);
            for(int seeds:{3,7,10}) {
                lim.seeds=seeds;auto got=solve(p,s,t,h,lim);
                for(auto& c:got.costs) c=original(c);
                std::sort(got.costs.begin(),got.costs.end());
                if(!got.complete || got.costs!=expected) throw std::runtime_error("brute-force mismatch at case "+std::to_string(tc));
            }
        } while(std::next_permutation(objective_order.begin(),objective_order.end()));
    }
    // Exponentially many nondominated paths, unsupported weighted-sum points,
    // equal first coordinates, zero cycles and parallel edges are all retained.
    std::vector<Raw> diamond;
    for(Node i=0;i<12;++i) {U w=1ULL<<i;diamond.push_back({i,i+1,{w,0,w}});diamond.push_back({i,i+1,{0,w,0}});}
    Graph g(13,diamond);lim.seeds=7;auto h=lower_bounds(g,12);auto r=solve(g,0,12,h,lim);
    if(!r.complete || r.costs.size()!=4096 || r.costs!=brute(g,0,12)) throw std::runtime_error("diamond mismatch");
    lim.max_expanded=1;r=solve(g,0,12,h,lim);
    if(r.complete || !r.costs.empty() || r.reason!="expansion_limit") throw std::runtime_error("partial result published");
    lim.max_expanded=0;lim.max_open=1;r=solve(g,0,12,h,lim);
    if(r.complete || !r.costs.empty() || r.reason!="open_limit") throw std::runtime_error("queue limit failed");
    lim.max_open=0;lim.max_seconds=1e-12;r=solve(g,0,12,h,lim);
    if(r.complete || !r.costs.empty() || r.reason!="time_limit") throw std::runtime_error("time limit failed");
    std::cout<<"SELF-TEST OK: 2000 multigraphs x 6 objective orders x 3 seed settings; zero costs/cycles, parallel edges, s=t, unreachable; 4096-point frontier; limits\n";
    return 0;
}

int main(int argc,char** argv) {
    try {
#ifdef _WIN32
        // MinGW main() receives ACP bytes, not UTF-8. Decode the native wide
        // command line before using u8path, including Chinese absolute paths.
        int count=0;auto wide=CommandLineToArgvW(GetCommandLineW(),&count);
        if(!wide) throw std::runtime_error("cannot decode command line");
        std::vector<std::string> utf8;utf8.reserve(count);
        for(int i=0;i<count;++i) {
            int n=WideCharToMultiByte(CP_UTF8,0,wide[i],-1,nullptr,0,nullptr,nullptr);
            std::string s(n,'\0');WideCharToMultiByte(CP_UTF8,0,wide[i],-1,s.data(),n,nullptr,nullptr);
            s.pop_back();utf8.push_back(std::move(s));
        }
        LocalFree(wide);
        std::vector<char*> pointers;for(auto& s:utf8) pointers.push_back(s.data());
        argc=count;argv=pointers.data();
#endif
        fs::path root=".",outdir="results_task2_exact";
        std::string ds_filter,query_filter,researcher="XXX";bool resume=false;U max_queries=0;Limits lim;
        for(int i=1;i<argc;++i) {
            std::string a=argv[i];
            auto value=[&](){if(i+1>=argc) throw std::runtime_error("missing value for "+a);return std::string(argv[++i]);};
            if(a=="--self-test") return self_test();
            else if(a=="--root") root=fs::u8path(value());
            else if(a=="--output-dir") outdir=fs::u8path(value());
            else if(a=="--dataset") ds_filter=value();
            else if(a=="--query-id") query_filter=value();
            else if(a=="--researcher") researcher=value();
            else if(a=="--max-queries") max_queries=number(value());
            else if(a=="--max-seconds") lim.max_seconds=number(value());
            else if(a=="--max-expanded" || a=="--benchmark-expanded") lim.max_expanded=number(value());
            else if(a=="--max-open") lim.max_open=number(value());
            else if(a=="--seed-count") {U z=number(value());if(z<3 || z>10) throw std::runtime_error("seed-count must be 3..10");lim.seeds=static_cast<int>(z);}
            else if(a=="--order") {
                order_text=value();auto sorted=order_text;std::sort(sorted.begin(),sorted.end());
                if(sorted!="123") throw std::runtime_error("order must be a permutation of 123");
                for(int j=0;j<3;++j) objective_order[j]=order_text[j]-'1';
            }
            else if(a=="--resume") resume=true;
            else if(a=="--quiet") lim.quiet=true;
            else if(a=="--help") {
                std::cout<<"task2_exact [--dataset NY|BAY|COL] [--query-id ID] [--max-queries N] [--output-dir DIR] [--researcher ID] [--resume]\n"
                         <<"  --max-seconds N: per-query search cap (excludes cached reverse Dijkstra / graph load); 0=unlimited\n"
                         <<"  --max-expanded N / --max-open N: exact-search resource caps, 0=unlimited\n"
                         <<"  --seed-count 3..10 (default 3); --order 123|132|213|231|312|321; --self-test; --quiet; --root DIR\n"
                         <<"Exit 0: requested scope complete; 2: incomplete, no partial vectors written; 1: error.\n";return 0;
            } else throw std::runtime_error("unknown option: "+a);
        }
        if(!ds_filter.empty() && ds_filter!="NY" && ds_filter!="BAY" && ds_filter!="COL") throw std::runtime_error("invalid dataset");
        if(!query_filter.empty() && !safe_id(query_filter)) throw std::runtime_error("invalid query ID");
        if(!safe_id(researcher)) throw std::runtime_error("invalid researcher ID");
        fs::path csv=outdir/fs::u8path(std::string("result2_\xe7\xa0\x94")+researcher+".csv");
        fs::path state=outdir/".task2_exact";
        if(!resume && (fs::exists(csv)||fs::exists(state))) throw std::runtime_error("output already exists: use --resume or a new directory");
        if(resume && fs::exists(csv) && !fs::exists(state/"version.txt")) throw std::runtime_error("legacy CSV cannot be resumed as verified exact output");
        if(fs::exists(state/"version.txt")) {
            std::ifstream in(state/"version.txt");std::string v;in>>v;if(v!=VERSION) throw std::runtime_error("checkpoint version mismatch");
        }
        std::vector<Query> all;std::map<std::string,fs::path> graph_paths;
        for(const std::string ds:{"NY","BAY","COL"}) {
            std::string low=ds;std::transform(low.begin(),low.end(),low.begin(),[](char c){return static_cast<char>(c-'A'+'a');});
            auto qp=root/"data"/("dimacs5_"+low)/"queries_problem2.csv";
            auto gp=root/"data"/"edges"/("edges_"+ds+"_5obj.txt");
            if(!fs::exists(qp)||!fs::exists(gp)) {
                if(ds_filter.empty()||ds_filter==ds) throw std::runtime_error("missing dataset "+ds);
                continue;
            }
            auto qs=read_queries(qp,ds);auto hash=fingerprint(gp,qp);graph_paths[ds]=gp;
            for(auto& q:qs) {q.fingerprint=hash;all.push_back(q);}
        }
        if(!query_filter.empty() && std::none_of(all.begin(),all.end(),[&](const Query& q){return q.id==query_filter && (ds_filter.empty()||q.dataset==ds_filter);}))
            throw std::runtime_error("query ID not found in selected dataset");
        fs::create_directories(state);atomic_write(state/"version.txt",std::string(VERSION)+"\n");
        std::map<std::string,Result> attempted;
        // Validate every retained checkpoint before touching the aggregate CSV.
        for(const auto& q:all) if(fs::exists(checkpoint(state,q))) restore(state,q);
        export_results(state,csv,all,attempted);
        U requested=0,complete=0;
        for(const auto& entry:graph_paths) {
            const auto& ds=entry.first;if(!ds_filter.empty() && ds!=ds_filter) continue;
            std::vector<Query> work;
            for(const auto& q:all) if(q.dataset==ds && (query_filter.empty() || q.id==query_filter) && (!max_queries || work.size()<max_queries)) work.push_back(q);
            requested+=work.size();
            bool pending=false;for(const auto& q:work) if(!fs::exists(checkpoint(state,q))) pending=true;
            if(!pending) {complete+=work.size();continue;}
            auto load_start=Clock::now();Graph g=Graph::load(entry.second);
            std::cerr<<ds<<" graph nodes="<<g.n<<" edges="<<g.edges.size()<<" order="<<order_text<<" load_s="<<seconds(load_start)<<'\n';
            // Group by target; only one reverse-distance cache is resident.
            std::stable_sort(work.begin(),work.end(),[](const Query& a,const Query& b){return a.t<b.t;});
            Node cached=UINT32_MAX;Heuristic h;
            for(const auto& q:work) {
                if(fs::exists(checkpoint(state,q))) {++complete;continue;}
                if(q.s>=g.n||q.t>=g.n) throw std::runtime_error("query node outside graph");
                if(cached!=q.t) {
                    auto hs=Clock::now();h=lower_bounds(g,q.t);cached=q.t;
                    std::cerr<<ds<<" target="<<cached<<" reverse_dijkstra_s="<<seconds(hs)<<'\n';
                }
                std::cerr<<"query "<<q.dataset<<'/'<<q.id<<" "<<q.s<<" -> "<<q.t<<'\n';
                auto r=solve(g,q.s,q.t,h,lim);
                for(auto& c:r.costs) c=original(c);
                std::sort(r.costs.begin(),r.costs.end());
                std::cerr<<"  status="<<r.reason<<" solutions="<<r.costs.size()<<" search_s="<<r.m.elapsed
                         <<" expanded="<<r.m.expanded<<" peak_open="<<r.m.peak_open<<" process_peak_MB="<<r.m.rss<<'\n';
                if(r.complete) {save(state,q,r);++complete;}
                else attempted[q.dataset+"/"+q.id]=std::move(r);
                export_results(state,csv,all,attempted);
            }
        }
        std::cout<<"requested_complete="<<complete<<'/'<<requested<<"; partial.csv until ALL input queries complete; consult task2_status.csv\n";
        return requested==complete?0:2;
    } catch(const std::exception& e) {std::cerr<<"ERROR: "<<e.what()<<'\n';return 1;}
}
