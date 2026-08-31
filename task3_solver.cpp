// Task 3: NAMOA*dr baseline and bounded OPEN apex merging.
// Goal witnesses are real paths; merged prefixes also retain a cost lower bound.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <queue>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#include <shellapi.h>
#else
#include <sys/resource.h>
#endif
using U=uint64_t;
using N=uint32_t;
using Cost=std::array<U,5>;
using Clock=std::chrono::steady_clock;
namespace fs=std::filesystem;
constexpr U INF=std::numeric_limits<U>::max()/4, DEN=1000000;
constexpr N NONE=UINT32_MAX;
static std::array<int,5> ORDER{1,0,2,3,4};
double elapsed(Clock::time_point t) {return std::chrono::duration<double>(Clock::now()-t).count();}
U number(const std::string& s) {
    if(s.empty()||s.find_first_not_of("0123456789")!=std::string::npos) throw std::runtime_error("invalid integer: "+s);
    return std::stoull(s);
}
U epsilon_number(std::string s) {
    auto p=s.find('.');
    if(p==std::string::npos) {U v=number(s);if(v>1000) throw std::runtime_error("epsilon too large");return v*DEN;}
    auto a=s.substr(0,p),b=s.substr(p+1);
    if(b.size()>6) throw std::runtime_error("epsilon supports at most six decimal places");
    while(b.size()<6) b+='0';
    U v=number(a.empty()?"0":a);
    if(v>1000) throw std::runtime_error("epsilon too large");
    return v*DEN+number(b);
}
U peak_mb() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS p{};
    if(GetProcessMemoryInfo(GetCurrentProcess(),&p,sizeof(p))) return p.PeakWorkingSetSize/(1024*1024);
#else
    rusage p{}; if(getrusage(RUSAGE_SELF,&p)==0) return U(p.ru_maxrss)/1024;
#endif
    return 0;
}
bool leq(const Cost& a,const Cost& b,int m) {for(int j=0;j<m;++j) if(a[j]>b[j]) return false;return true;}
Cost add(const Cost& a,const Cost& b) {Cost z{};for(int j=0;j<5;++j) {if(a[j]>=INF-b[j]) throw std::runtime_error("cost overflow");z[j]=a[j]+b[j];}return z;}
struct Raw {N u,v;Cost c;};
struct Edge {N to;std::array<N,5> c;};
struct Back {N from,edge;};
struct Graph {
    N n;std::vector<N> off,roff;std::vector<Edge> edges;std::vector<Back> reverse;
    Graph(N nn,const std::vector<Raw>& raw):n(nn),off(n+1),roff(n+1) {
        if(raw.size()>=NONE) throw std::runtime_error("too many edges");
        for(auto& e:raw) {
            if(e.u>=n||e.v>=n) throw std::runtime_error("invalid endpoint");
            for(U x:e.c) if(x>UINT32_MAX || (__int128)x*(2ULL*n+1)>=INF) throw std::runtime_error("edge cost out of range");
            ++off[e.u+1];++roff[e.v+1];
        }
        for(N i=1;i<=n;++i) {off[i]+=off[i-1];roff[i]+=roff[i-1];}
        edges.resize(raw.size());reverse.resize(raw.size());auto a=off,b=roff;
        for(auto& e:raw) {N k=a[e.u]++;edges[k].to=e.v;for(int j=0;j<5;++j) edges[k].c[j]=N(e.c[j]);reverse[b[e.v]++]={e.u,k};}
    }
    static Graph load(const fs::path& path) {
        std::ifstream in(path);if(!in) throw std::runtime_error("cannot open edge file");
        std::string line;std::vector<Raw> raw;N n=0;
        while(std::getline(in,line)) {
            auto p=line.find_first_not_of(" \t\r");if(p==std::string::npos||line[p]=='#') continue;
            std::istringstream row(line);std::array<std::string,7> v;std::string extra;
            for(auto& s:v) if(!(row>>s)) throw std::runtime_error("truncated edge row");
            if(row>>extra) throw std::runtime_error("extra edge field");
            U u=number(v[0]),w=number(v[1]);if(u>=NONE-1||w>=NONE-1) throw std::runtime_error("node too large");
            Raw e{N(u),N(w),{}};for(int j=0;j<5;++j) e.c[j]=number(v[j+2]);
            raw.push_back(e);n=std::max(n,N(std::max(u,w)+1));
        }
        if(!in.eof()||!n) throw std::runtime_error("empty or invalid graph");
        return Graph(n,raw);
    }
    Cost cost(N k) const {Cost c{};for(int j=0;j<5;++j) c[j]=edges[k].c[j];return c;}
};
struct Path {Cost c{};std::vector<N> vertices,edges;};
Path make_path(const Graph& g,N s,N t,const std::vector<N>& indices) {
    Path p;p.vertices.push_back(s);N v=s;
    for(N k:indices) {
        if(k<g.off[v]||k>=g.off[v+1]) throw std::runtime_error("parent edge mismatch");
        v=g.edges[k].to;p.vertices.push_back(v);p.edges.push_back(k);p.c=add(p.c,g.cost(k));
    }
    if(v!=t) throw std::runtime_error("path does not end at target");
    auto nodes=p.vertices;std::sort(nodes.begin(),nodes.end());
    if(std::adjacent_find(nodes.begin(),nodes.end())!=nodes.end()) throw std::runtime_error("path contains a cycle");
    return p;
}
bool archive_insert(std::vector<Path>& a,Path p,int m) {
    for(auto& q:a) if(leq(q.c,p.c,m)) return false;
    a.erase(std::remove_if(a.begin(),a.end(),[&](const Path& q){return leq(p.c,q.c,m);}),a.end());
    a.push_back(std::move(p));return true;
}
bool covered(const std::vector<Path>& a,const Cost& f,int m,U eps) {
    for(auto& p:a) {
        bool ok=true;
        for(int j=0;j<m;++j) if((__int128)p.c[j]*DEN>(__int128)(DEN+eps)*f[j]) {ok=false;break;}
        if(ok) return true;
    }
    return false;
}
struct Prepared {std::vector<Cost> h;std::vector<Path> seeds;};
Prepared prepare(const Graph& g,N s,N t,int m,int seed_count) {
    Prepared p;p.h.resize(g.n);for(auto& c:p.h) c.fill(INF);
    using Item=std::pair<U,N>;
    for(int j=0;j<m;++j) {
        std::priority_queue<Item,std::vector<Item>,std::greater<Item>> q;
        std::vector<N> next(g.n,NONE);p.h[t][j]=0;q.push({0,t});
        while(!q.empty()) {
            auto [d,v]=q.top();q.pop();if(d!=p.h[v][j]) continue;
            for(N k=g.roff[v];k<g.roff[v+1];++k) {
                auto b=g.reverse[k];U nd=d+g.edges[b.edge].c[j];
                if(nd<p.h[b.from][j]) {p.h[b.from][j]=nd;next[b.from]=b.edge;q.push({nd,b.from});}
            }
        }
        if(p.h[s][j]==INF) continue;
        std::vector<N> path;N v=s;
        while(v!=t) {N k=next[v];if(k==NONE||path.size()>=g.n) throw std::runtime_error("invalid shortest-path tree");path.push_back(k);v=g.edges[k].to;}
        archive_insert(p.seeds,make_path(g,s,t,path),m);
    }
    if(p.h[s][0]==INF) return p;
    // Normalized weighted Dijkstra paths only initialize the feasible archive;
    // they never serve as heuristic lower bounds or a coverage certificate.
    std::mt19937 rng(3405);
    for(int r=m;r<seed_count;++r) {
        std::array<long double,5> w{};
        for(int j=0;j<m;++j) w[j]=(r==m?1.0L:std::pow(10.0L,(int(rng()%401)-200)/100.0L))/std::max<U>(1,p.h[s][j]);
        using WItem=std::pair<long double,N>;
        std::vector<long double> d(g.n,std::numeric_limits<long double>::infinity());
        std::vector<N> prev(g.n,NONE),from(g.n,NONE);std::vector<bool> settled(g.n);
        std::priority_queue<WItem,std::vector<WItem>,std::greater<WItem>> q;d[s]=0;q.push({0,s});
        while(!q.empty()) {
            auto [dv,v]=q.top();q.pop();if(settled[v]||dv!=d[v]) continue;settled[v]=true;if(v==t) break;
            for(N k=g.off[v];k<g.off[v+1];++k) {
                auto& e=g.edges[k];if(settled[e.to]) continue;long double nd=dv;
                for(int j=0;j<m;++j) nd+=w[j]*e.c[j];
                if(nd<d[e.to]) {d[e.to]=nd;prev[e.to]=k;from[e.to]=v;q.push({nd,e.to});}
            }
        }
        std::vector<N> path;N v=t;
        while(v!=s) {if(prev[v]==NONE||path.size()>=g.n) throw std::runtime_error("invalid weighted predecessor");path.push_back(prev[v]);v=from[v];}
        std::reverse(path.begin(),path.end());archive_insert(p.seeds,make_path(g,s,t,path),m);
    }
    return p;
}
// Closed labels only: the first active coordinate is ordered by consistent f.
// For m=2 use a scalar; for m=3 binary-search a sorted two-coordinate skyline.
struct Skyline {
    U best=INF;std::vector<std::array<U,4>> a;
    bool dominates(const Cost& c,int m) const {
        if(m==2) return best<=c[ORDER[1]];
        if(m==3) {
            auto it=std::upper_bound(a.begin(),a.end(),c[ORDER[1]],[](U v,const auto& p){return v<p[0];});
            return it!=a.begin()&&std::prev(it)->at(1)<=c[ORDER[2]];
        }
        for(auto& p:a) {bool ok=true;for(int j=1;j<m;++j) if(p[j-1]>c[ORDER[j]]) {ok=false;break;}if(ok) return true;}
        return false;
    }
    void insert(const Cost& c,int m) {
        if(m==2) {best=c[ORDER[1]];return;}
        std::array<U,4> p{};for(int j=1;j<m;++j) p[j-1]=c[ORDER[j]];
        if(m==3) {
            auto it=std::lower_bound(a.begin(),a.end(),p[0],[](const auto& x,U v){return x[0]<v;});
            auto end=it;while(end!=a.end()&&(*end)[1]>=p[1]) ++end;
            it=a.erase(it,end);a.insert(it,p);return;
        }
        a.erase(std::remove_if(a.begin(),a.end(),[&](const auto& x){for(int j=0;j<m-1;++j) if(p[j]>x[j]) return false;return true;}),a.end());a.push_back(p);
    }
};
struct Label {Cost g;N v,parent,edge;};
struct Config {int m=3,seeds=12;U eps=100000,max_labels=2000000,max_expanded=0;double max_seconds=60;bool seed_only=false;std::string algorithm="apex",order="21345";};
struct Result {
    std::vector<Path> paths;std::string status;bool certified=false;
    U labels=0,expanded=0,open_peak=0,popped=0;size_t seed_size=0;
    U merged=0,merge_checks=0;
    double preprocess_seconds=0,search_seconds=0;
};
Result solve_baseline(const Graph& g,N s,N t,const Config& c) {
    if(s>=g.n||t>=g.n) throw std::runtime_error("query outside graph");
    auto start=Clock::now();auto prep=prepare(g,s,t,c.m,c.seeds);Result out;
    out.preprocess_seconds=elapsed(start);out.paths=std::move(prep.seeds);out.seed_size=out.paths.size();
    if(prep.h[s][0]==INF) {out.status="unreachable";out.certified=true;return out;}
    if(c.seed_only) {out.status="seed_only";return out;}
    start=Clock::now();std::vector<Label> labels;labels.reserve(size_t(std::min<U>(c.max_labels,65536)));
    std::vector<Skyline> closed(g.n);
    auto compare=[&](N a,N b) {
        auto& x=labels[a];auto& y=labels[b];
        for(int k=0;k<c.m;++k) {int j=ORDER[k];U u=x.g[j]+prep.h[x.v][j],v=y.g[j]+prep.h[y.v][j];if(u!=v) return u>v;}
        return a>b;
    };
    std::priority_queue<N,std::vector<N>,decltype(compare)> open(compare);
    labels.push_back({{},s,NONE,NONE});open.push(0);out.status="running";
    auto fcost=[&](const Cost& cost,N v){Cost f{};for(int j=0;j<c.m;++j) f[j]=cost[j]+prep.h[v][j];return f;};
    bool stop=false;
    while(!open.empty()&&!stop) {
        if((out.popped%1024==0)&&c.max_seconds>0&&elapsed(start)>=c.max_seconds) {out.status="time_limit";break;}
        N id=open.top();open.pop();++out.popped;const Label p=labels[id]; // copy before vector growth
        if(closed[p.v].dominates(p.g,c.m)||covered(out.paths,fcost(p.g,p.v),c.m,c.eps)) continue;
        if(p.v==t) {
            std::vector<N> indices;for(N k=id;labels[k].parent!=NONE;k=labels[k].parent) indices.push_back(labels[k].edge);
            std::reverse(indices.begin(),indices.end());auto path=make_path(g,s,t,indices);
            if(path.c!=p.g) throw std::runtime_error("recovered cost mismatch");
            archive_insert(out.paths,std::move(path),c.m);continue;
        }
        if(c.max_expanded&&out.expanded>=c.max_expanded) {out.status="expansion_limit";break;}
        closed[p.v].insert(p.g,c.m);++out.expanded;
        for(N k=g.off[p.v];k<g.off[p.v+1];++k) {
            N v=g.edges[k].to;if(prep.h[v][0]==INF) continue;Cost cost=add(p.g,g.cost(k));
            if(closed[v].dominates(cost,c.m)||covered(out.paths,fcost(cost,v),c.m,c.eps)) continue;
            if(labels.size()>=c.max_labels) {out.status="label_limit";stop=true;break;}
            labels.push_back({cost,v,id,k});open.push(N(labels.size()-1));
        }
        out.open_peak=std::max<U>(out.open_peak,open.size());
    }
    if(!stop&&open.empty()&&out.status=="running") {out.certified=true;out.status=c.eps?"epsilon_cover":"exact";}
    out.labels=labels.size();out.search_seconds=elapsed(start);
    std::sort(out.paths.begin(),out.paths.end(),[](const Path& a,const Path& b){return a.c<b.c;});return out;
}

// OPEN-only apex merging. A is a componentwise lower bound for the represented
// prefixes, while g is the cost of one REAL path. The invariant is
//   g+h <= (1+epsilon)*(A+h), checked with exact integer arithmetic.
// It is preserved under extension by consistency of h. Unlike epsilon pruning
// between ordinary prefixes, repeated merges cannot accumulate extra error.
struct ApexLabel {Cost a,g;N v,parent,edge;U version=0;bool queued=true;};
struct HeapItem {Cost f;N id;U version;};
bool bounded(const Cost& g,const Cost& a,const Cost& h,int m,U eps) {
    for(int j=0;j<m;++j)
        if((__int128)(g[j]+h[j])*DEN>(__int128)(DEN+eps)*(a[j]+h[j])) return false;
    return true;
}
long double worst_ratio(const Cost& g,const Cost& a,const Cost& h,int m) {
    long double worst=1;
    for(int j=0;j<m;++j) {
        U den=a[j]+h[j];
        if(den) worst=std::max(worst,(long double)(g[j]+h[j])/den);
    }
    return worst; // selection only; acceptance never relies on floating point
}
Path simplify_walk(const Graph& g,N s,N t,const std::vector<N>& walk,const Cost& expected) {
    std::vector<N> vertices{s},edges;std::unordered_map<N,size_t> position{{s,0}};
    N v=s;Cost total{};
    for(N k:walk) {
        if(k<g.off[v]||k>=g.off[v+1]) throw std::runtime_error("apex parent edge mismatch");
        total=add(total,g.cost(k));v=g.edges[k].to;
        auto found=position.find(v);
        if(found!=position.end()) {
            size_t keep=found->second;
            while(vertices.size()>keep+1) {position.erase(vertices.back());vertices.pop_back();}
            edges.resize(keep);
        } else {edges.push_back(k);position[v]=vertices.size();vertices.push_back(v);}
    }
    if(v!=t||total!=expected) throw std::runtime_error("apex recovered walk mismatch");
    // Removing a nonnegative-cost cycle can only improve the coverage witness.
    return make_path(g,s,t,edges);
}
Result solve_apex(const Graph& g,N s,N t,const Config& c) {
    if(c.eps==0||c.seed_only) return solve_baseline(g,s,t,c);
    if(s>=g.n||t>=g.n) throw std::runtime_error("query outside graph");
    auto start=Clock::now();auto prep=prepare(g,s,t,c.m,c.seeds);Result out;
    out.preprocess_seconds=elapsed(start);out.paths=std::move(prep.seeds);out.seed_size=out.paths.size();
    if(prep.h[s][0]==INF) {out.status="unreachable";out.certified=true;return out;}
    start=Clock::now();std::vector<ApexLabel> labels;labels.reserve(size_t(std::min<U>(c.max_labels,65536)));
    std::vector<Skyline> closed(g.n);std::vector<std::vector<N>> pending(g.n);
    auto compare=[&](const HeapItem& a,const HeapItem& b) {
        for(int k=0;k<c.m;++k) {int j=ORDER[k];if(a.f[j]!=b.f[j]) return a.f[j]>b.f[j];}
        return a.id>b.id;
    };
    std::priority_queue<HeapItem,std::vector<HeapItem>,decltype(compare)> open(compare);
    auto fcost=[&](const Cost& a,N v){Cost f{};for(int j=0;j<c.m;++j) f[j]=a[j]+prep.h[v][j];return f;};
    auto push=[&](N id){auto& p=labels[id];open.push({fcost(p.a,p.v),id,p.version});out.open_peak=std::max<U>(out.open_peak,open.size());};
    labels.push_back({{},{},s,NONE,NONE});pending[s].push_back(0);push(0);out.status="running";
    bool stop=false;
    while(!open.empty()&&!stop) {
        if(out.popped%1024==0&&c.max_seconds>0&&elapsed(start)>=c.max_seconds) {out.status="time_limit";break;}
        HeapItem item=open.top();open.pop();++out.popped;
        if(!labels[item.id].queued||labels[item.id].version!=item.version) continue;
        labels[item.id].queued=false;const ApexLabel p=labels[item.id];
        if(closed[p.v].dominates(p.a,c.m)||covered(out.paths,item.f,c.m,c.eps)) continue;
        if(!bounded(p.g,p.a,prep.h[p.v],c.m,c.eps)) throw std::runtime_error("apex invariant failed");
        if(p.v==t) {
            std::vector<N> walk;
            for(N k=item.id;labels[k].parent!=NONE;k=labels[k].parent) {
                if(walk.size()>=labels.size()) throw std::runtime_error("cyclic parent chain");
                walk.push_back(labels[k].edge);
            }
            std::reverse(walk.begin(),walk.end());archive_insert(out.paths,simplify_walk(g,s,t,walk,p.g),c.m);continue;
        }
        if(c.max_expanded&&out.expanded>=c.max_expanded) {out.status="expansion_limit";break;}
        closed[p.v].insert(p.a,c.m);++out.expanded;
        for(N k=g.off[p.v];k<g.off[p.v+1];++k) {
            N v=g.edges[k].to;if(prep.h[v][0]==INF) continue;
            Cost a=add(p.a,g.cost(k)),cost=add(p.g,g.cost(k));
            if(closed[v].dominates(a,c.m)||covered(out.paths,fcost(a,v),c.m,c.eps)) continue;
            auto& list=pending[v];
            list.erase(std::remove_if(list.begin(),list.end(),[&](N id){return !labels[id].queued;}),list.end());
            bool merged=false;
            for(N id:list) {
                ++out.merge_checks;auto& old=labels[id];Cost low=a;
                for(int j=0;j<c.m;++j) low[j]=std::min(a[j],old.a[j]);
                bool old_ok=bounded(old.g,low,prep.h[v],c.m,c.eps),new_ok=bounded(cost,low,prep.h[v],c.m,c.eps);
                if(!old_ok&&!new_ok) continue;
                bool choose_new=new_ok&&(!old_ok||worst_ratio(cost,low,prep.h[v],c.m)<worst_ratio(old.g,low,prep.h[v],c.m));
                bool changed=false;for(int j=0;j<c.m;++j) if(low[j]!=old.a[j]) changed=true;
                old.a=low;
                if(choose_new) {old.g=cost;old.parent=item.id;old.edge=k;}
                // Only OPEN labels are mutable. Every parent was already expanded
                // and will never change, even when the parent has a larger ID.
                if(changed) {++old.version;push(id);} // immutable heap key + lazy stale removal
                ++out.merged;merged=true;break;
            }
            if(merged) continue;
            if(labels.size()>=c.max_labels) {out.status="label_limit";stop=true;break;}
            labels.push_back({a,cost,v,item.id,k});N id=N(labels.size()-1);list.push_back(id);push(id);
        }
    }
    if(!stop&&open.empty()&&out.status=="running") {out.certified=true;out.status="epsilon_cover";}
    out.labels=labels.size();out.search_seconds=elapsed(start);
    std::sort(out.paths.begin(),out.paths.end(),[](const Path& a,const Path& b){return a.c<b.c;});return out;
}
void write_result(const fs::path& path,const Graph& g,N s,N t,const Config& c,const Result& r,double load_seconds,double total_seconds) {
    if(fs::exists(path)) throw std::runtime_error("output already exists (choose a new file)");
    if(!path.parent_path().empty()) fs::create_directories(path.parent_path());
    std::ofstream out(path);if(!out) throw std::runtime_error("cannot create output");
    out<<std::setprecision(10)<<"{\n\"schema\":\"TASK3_V1\",\"source\":"<<s<<",\"target\":"<<t<<",\"objective_count\":"<<c.m
       <<",\"epsilon\":"<<double(c.eps)/DEN<<",\"epsilon_numerator\":"<<c.eps<<",\"epsilon_denominator\":"<<DEN
       <<",\"seed_count\":"<<c.seeds<<",\"seed_only\":"<<(c.seed_only?"true":"false")
       <<",\"algorithm\":\""<<c.algorithm<<"\",\"merged\":"<<r.merged<<",\"merge_checks\":"<<r.merge_checks
       <<",\"order\":\""<<c.order<<"\""
       <<",\"status\":\""<<r.status<<"\",\"certified\":"<<(r.certified?"true":"false")
       <<",\"nodes\":"<<g.n<<",\"edges\":"<<g.edges.size()<<",\"seed_size\":"<<r.seed_size
       <<",\"labels\":"<<r.labels<<",\"expanded\":"<<r.expanded<<",\"open_peak\":"<<r.open_peak
       <<",\"load_seconds\":"<<load_seconds<<",\"preprocess_seconds\":"<<r.preprocess_seconds
       <<",\"search_seconds\":"<<r.search_seconds<<",\"total_seconds\":"<<total_seconds
       <<",\"peak_rss_mb\":"<<peak_mb()<<",\"paths\":[\n";
    bool first=true;for(auto& p:r.paths) {
        if(!first) out<<",\n";
        first=false;out<<"{\"cost\":[";
        for(int j=0;j<5;++j) {if(j) out<<',';out<<p.c[j];}out<<"],\"vertices\":[";
        for(size_t j=0;j<p.vertices.size();++j) {if(j) out<<',';out<<p.vertices[j];}out<<"],\"edge_indices\":[";
        for(size_t j=0;j<p.edges.size();++j) {if(j) out<<',';out<<p.edges[j];}out<<"]}";
    }
    out<<"\n]}\n";out.close();if(!out) throw std::runtime_error("result write failed");
}
int main(int argc,char** argv) {
    try {
        std::vector<std::string> args;
#ifdef _WIN32
        int count=0;LPWSTR* wide=CommandLineToArgvW(GetCommandLineW(),&count);
        if(!wide) throw std::runtime_error("cannot decode command line");
        for(int i=1;i<count;++i) {int n=WideCharToMultiByte(CP_UTF8,0,wide[i],-1,nullptr,0,nullptr,nullptr);std::string v(n,'\0');WideCharToMultiByte(CP_UTF8,0,wide[i],-1,v.data(),n,nullptr,nullptr);v.pop_back();args.push_back(v);}LocalFree(wide);(void)argc;(void)argv;
#else
        for(int i=1;i<argc;++i) args.push_back(argv[i]);
#endif
        Config c;fs::path edges,output;N s=NONE,t=NONE;
        for(size_t i=0;i<args.size();++i) {
            auto key=args[i];if(key=="--seed-only") {c.seed_only=true;continue;}
            if(key=="--help") {std::cout<<"--edges FILE --source N --target N --objectives 2|3|5 --epsilon 0.1 --output FILE [--algorithm apex|baseline --order 21345 --seeds 12 --max-seconds 60 --max-labels 2000000 --max-expanded 0 --seed-only]\n";return 0;}
            if(i+1==args.size()) throw std::runtime_error("missing argument value");
            auto v=args[++i];
            if(key=="--edges") edges=fs::u8path(v);else if(key=="--output") output=fs::u8path(v);
            else if(key=="--source"||key=="--target") {U n=number(v);if(n>=NONE) throw std::runtime_error("node too large");(key=="--source"?s:t)=N(n);}
            else if(key=="--objectives") {U n=number(v);if(n!=2&&n!=3&&n!=5) throw std::runtime_error("objectives must be 2, 3 or 5");c.m=int(n);}
            else if(key=="--epsilon") c.eps=epsilon_number(v);
            else if(key=="--algorithm") {if(v!="apex"&&v!="baseline") throw std::runtime_error("algorithm must be apex or baseline");c.algorithm=v;}
            else if(key=="--order") c.order=v;
            else if(key=="--seeds") {U n=number(v);if(n>100) throw std::runtime_error("too many seeds");c.seeds=int(n);}
            else if(key=="--max-seconds") {size_t pos=0;c.max_seconds=std::stod(v,&pos);if(pos!=v.size()||!std::isfinite(c.max_seconds)||c.max_seconds<0) throw std::runtime_error("invalid time limit");}
            else if(key=="--max-labels") c.max_labels=number(v);
            else if(key=="--max-expanded") c.max_expanded=number(v);
            else throw std::runtime_error("unknown option: "+key);
        }
        if(edges.empty()||output.empty()||s==NONE||t==NONE) throw std::runtime_error("edges, source, target and output are required");
        if(c.seeds<c.m||c.max_labels<1||c.max_labels>=NONE) throw std::runtime_error("invalid seeds or label limit");
        auto sorted=c.order;std::sort(sorted.begin(),sorted.end());
        if(sorted!="12345") throw std::runtime_error("order must be a permutation of 12345");
        size_t pos=0;for(char j:c.order) if(j-'1'<c.m) ORDER[pos++]=j-'1';
        for(char j:c.order) if(j-'1'>=c.m) ORDER[pos++]=j-'1';
        auto start=Clock::now();Graph g=Graph::load(edges);double load_seconds=elapsed(start);
        Result r=c.algorithm=="apex"?solve_apex(g,s,t,c):solve_baseline(g,s,t,c);write_result(output,g,s,t,c,r,load_seconds,elapsed(start));
        std::cout<<"status="<<r.status<<" paths="<<r.paths.size()<<" certified="<<r.certified<<" search_s="<<r.search_seconds<<" peak_mb="<<peak_mb()<<'\n';
        return 0;
    } catch(const std::exception& e) {std::cerr<<"ERROR: "<<e.what()<<'\n';return 1;}
}
